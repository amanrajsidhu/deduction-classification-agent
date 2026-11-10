"""Offline replay of exported workflow code; never invokes a provider or n8n.

Replays *persisted final proposals*, not unavailable raw provider responses.
Development proposals are hand-authored controls, not measured model predictions.
The development route expectations describe the pre-correction workflow; use
--workflow with its saved before-workflow snapshot to reproduce that history.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

try:
    from .generate_xlsx_output import (
        compute_metrics, load_answer_key, load_run_outputs, load_source_accruals,
    )
except ImportError:
    from generate_xlsx_output import (
        compute_metrics, load_answer_key, load_run_outputs, load_source_accruals,
    )

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "workflows/DEDUCTION_RESOLUTION_WORKBENCH_V2.json"
DEVELOPMENT = ROOT / "fixtures/development/context_feasibility.json"

DRIVER = r"""
const fs = require('fs');
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
const workflow = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
const node = name => workflow.nodes.find(n => n.name === name);
const items = rows => rows.map(json => ({ json }));
const execute = (name, rows, lookup) => new Function('$input', '$', node(name).parameters.jsCode)(
  { all: () => items(rows) }, lookup || (() => { throw Error('Unexpected node dependency'); })
);
function replay(settlements, accruals, proposals) {
  const normalS = execute('Code (Settlement: normalise + key)', settlements).map(i => i.json);
  const normalA = execute('Code (Accrual: normalise + key)', accruals).map(i => i.json);
  const deterministic = execute('Code (Deterministic Match: one-to-one)', [...normalS, ...normalA]);
  const unmatched = deterministic.map(i => i.json).filter(j => j._route === 'needs_classification');
  const proposalById = new Map(proposals.map(p => [p.deduction_id, p]));
  const batches = new Map();
  for (const row of unmatched) {
    const p = proposalById.get(row.deduction_id);
    if (!p) throw Error('Missing replay proposal: ' + row.deduction_id);
    const key = p._llm_batch_ref || 'simulated-development-batch';
    if (!batches.has(key)) batches.set(key, []);
    batches.get(key).push(row);
  }
  const parsed = [];
  const promptShapes = [];
  for (const rows of batches.values()) {
    const built = execute('Code (Build Classification Prompt)', rows)[0].json;
    const payload = JSON.parse(built.request_body.messages[0].content);
    promptShapes.push({ model: built.request_body.model, row_count: rows.length, fields: Object.keys(payload[0]) });
    const first = proposalById.get(rows[0].deduction_id);
    const response = { stop_reason: 'tool_use', usage: {
      input_tokens: first.input_tokens ?? null, output_tokens: first.output_tokens ?? null,
      cache_creation_input_tokens: first.cache_creation_input_tokens || 0,
      cache_read_input_tokens: first.cache_read_input_tokens || 0
    }, content: [{ type: 'tool_use', name: 'submit_classifications', input: {
      classifications: rows.map(row => {
        const p = proposalById.get(row.deduction_id);
        return { deduction_id: row.deduction_id, bucket: p.llm_bucket, confidence: p.llm_confidence ?? 0,
          reasoning: 'OFFLINE SIMULATION: persisted proposal or hand-authored development stub' };
      })
    }}] };
    parsed.push(...execute('Code (Parse Classification Response)', [response], name => {
      if (name !== 'Code (Build Classification Prompt)') throw Error('Unexpected parser lookup');
      return { first: () => ({ json: built }) };
    }));
  }
  const lookup = name => {
    if (name !== 'Code (Deterministic Match: one-to-one)') throw Error('Unexpected allocator lookup');
    return { all: () => deterministic };
  };
  const verified = execute('Code (Verify Classification Against Evidence)', parsed.map(i => i.json), lookup);
  const exports = execute('Code (Build Complete Branch Exports)', verified.map(i => i.json), lookup);
  const branches = Object.fromEntries(exports.map(item => [
    item.json.fileName, JSON.parse(Buffer.from(item.binary.data.data, 'base64').toString('utf8'))
  ]));
  return { branches, prompt_shapes: promptShapes, unmatched_count: unmatched.length };
}
const baseline = replay(data.settlements, data.accruals, data.proposals);
const development = [];
for (const example of data.development.cases) {
  const rows = example.rows.map(row => ({ ...data.development.common_row, ...row }));
  const pools = example.pools.map(pool => ({ ...data.development.common_pool, ...pool }));
  for (const variant of example.variants) {
    const proposals = rows.map((row, index) => ({ deduction_id: row.deduction_id, llm_bucket: variant.buckets[index] }));
    const run = replay(rows, pools, proposals);
    const byId = new Map(Object.values(run.branches).flat().map(row => [row.deduction_id, row]));
    development.push({ case_id: example.id, variant: variant.name, rows: rows.map(row => byId.get(row.deduction_id)) });
  }
}
process.stdout.write(JSON.stringify({ baseline, development }));
"""


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/feasibility-2026-10-26")
    parser.add_argument("--workflow", type=Path, default=WORKFLOW,
                        help="Use the preserved before-workflow for historical development expectations")
    args = parser.parse_args()
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node is required to execute the exported JavaScript")
    saved, problems = load_run_outputs(ROOT / "outputs/v2")
    if problems:
        raise ValueError(problems)
    examples = json.loads(DEVELOPMENT.read_text(encoding="utf-8"))
    payload = {
        "settlements": read_csv(ROOT / "fixtures/v2/settlement_deductions.csv"),
        "accruals": read_csv(ROOT / "fixtures/v2/invoice_accruals.csv"),
        "proposals": saved["classified_verified"] + saved["unresolvable"] + saved["needs_review"],
        "development": examples,
    }
    completed = subprocess.run(
        [node, "-e", DRIVER, str(args.workflow)], input=json.dumps(payload),
        text=True, capture_output=True, check=True, timeout=30,
    )
    result = json.loads(completed.stdout)
    replay_dir = args.output_dir / "deterministic-replay"
    replay_dir.mkdir(parents=True, exist_ok=True)
    for filename, rows in result["baseline"]["branches"].items():
        (replay_dir / filename).write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    replayed, replay_problems = load_run_outputs(replay_dir)
    _, truth = load_answer_key(ROOT / "fixtures/v2/answer_key.json.gz")
    accruals, accrual_problems = load_source_accruals(ROOT / "fixtures/v2/invoice_accruals.csv")
    metrics = compute_metrics(replayed, truth, replay_problems, accruals, accrual_problems)
    original = compute_metrics(saved, truth, [], accruals, accrual_problems)
    differences = {
        key: {"saved": original[key], "replay": metrics.get(key)}
        for key in original if key != "generated_at_utc" and original[key] != metrics.get(key)
    }
    if differences:
        raise AssertionError(f"Deterministic replay metrics diverged: {differences}")
    compared_fields = (
        "_route", "matched_accrual_id", "matched_bucket", "llm_bucket", "_classification_method",
        "_evidence_accrual_id", "_allocated_amount", "_evidence_balance_before", "_evidence_balance_after",
    )
    for branch, expected_rows in saved.items():
        actual_by_id = {row["deduction_id"]: row for row in replayed[branch]}
        if set(actual_by_id) != {row["deduction_id"] for row in expected_rows}:
            raise AssertionError(f"Branch membership differs: {branch}")
        for row in expected_rows:
            for field in compared_fields:
                if row.get(field) != actual_by_id[row["deduction_id"]].get(field):
                    raise AssertionError(f"Replay differs: {row['deduction_id']} {field}")
    examples_by_id = {case["id"]: case for case in examples["cases"]}
    for observation in result["development"]:
        case = examples_by_id[observation["case_id"]]
        variant = next(item for item in case["variants"] if item["name"] == observation["variant"])
        routes = [row["_route"] for row in observation["rows"]]
        buckets = [row.get("llm_bucket") for row in observation["rows"]]
        if routes != variant["expected_current_routes"] or buckets != variant["expected_current_buckets"]:
            raise AssertionError(f"Unexpected current behavior: {observation['case_id']}")
        observation["matches_inspected_current_behavior"] = True
        observation["proposed_business_expectation"] = case["proposed_business_expectation"]
        observation["demonstrated_limitation"] = variant.get("demonstrated_limitation")
        if "evaluation_expectation" in case:
            expected = case["evaluation_expectation"]
            observed_branches = {key: [] for key in saved}
            for row in observation["rows"]:
                observed_branches[row["_route"]].append(row)
            pools = [{**examples["common_pool"], **pool} for pool in case["pools"]]
            evaluated = compute_metrics(
                observed_branches, {expected["deduction_id"]: expected}, [], pools, [],
            )
            wrong = variant["name"] == "wrong_supported_proposal"
            if evaluated["terminal_misroute_count"] != int(wrong):
                raise AssertionError("Evaluator did not distinguish correct and wrong supported proposals")
            if wrong and expected["deduction_id"] not in evaluated["invalid_evidence_semantic_ids"]:
                raise AssertionError("Wrong intended support was not detected")
            observation["independent_evaluator"] = {
                key: evaluated[key] for key in (
                    "terminal_misroute_count", "terminal_misroute_value_gbp", "classification_precision",
                    "invalid_evidence_semantic_ids", "source_allocation_integrity",
                )
            }
    evidence = {
        "provider_calls": 0, "provider_spend_gbp": 0,
        "provenance": "Saved final-proposal replay and hand-authored development stubs; not new model performance",
        "workflow_sha256": hashlib.sha256(args.workflow.read_bytes()).hexdigest(),
        "development_sha256": hashlib.sha256(DEVELOPMENT.read_bytes()).hexdigest(),
        "replay_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "baseline_metrics_identical_except_timestamp": True,
        "baseline_branch_membership_and_control_fields_identical": True,
        "prompt_shapes": result["baseline"]["prompt_shapes"],
        "baseline_metrics": metrics,
        "development_observations": result["development"],
        "limits": ["No HTTP node, n8n engine, Docker mount, provider availability or new model output tested",
                   "Persisted final proposals cannot reconstruct original raw AI responses overwritten by aliases",
                   "Development stub confidence is not calibrated or measured model confidence"],
    }
    target = args.output_dir / "replay_evidence.json"
    target.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"Baseline deterministic replay: exact metric/control-field match, {metrics['unique_routed_lines']} rows")
    print(f"Development controls: {len(result['development'])} variants across {len(examples['cases'])} scenarios")
    print("Provider calls: 0; provider spend: GBP 0")
    print(f"Evidence: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
