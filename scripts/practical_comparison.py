"""Prepare unsent requests and equal-evidence development inputs. No provider access.

Expected outcomes are kept outside both classifier inputs. Scoring waits for
the user's predictions to be recorded. All candidate model answers are simulated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

try:
    from .deduction_rules import canonical_vendor
except ImportError:
    from deduction_rules import canonical_vendor

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "fixtures/development/practical_inputs.json"
EXPECTATIONS = ROOT / "fixtures/development/practical_expectations.json"
WORKFLOW = ROOT / "workflows/DEDUCTION_RESOLUTION_WORKBENCH_V2.json"
DEFAULT_OUTPUT = ROOT / "outputs/practical-2026-10-26"

PREPARE_DRIVER = r"""
const fs = require('fs');
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
const workflow = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
const promptNode = workflow.nodes.find(n => n.name === 'Code (Build Classification Prompt)');
const build = new Function('$input', promptNode.parameters.jsCode);
const requests = data.cases.map(example => {
  const row = { ...data.common_row, ...example.row };
  const built = build({ all: () => [{ json: row }] })[0].json;
  const currentRequest = built.request_body;
  const evidence = {
    deduction_lines: JSON.parse(currentRequest.messages[0].content),
    guide_sources: example.sources,
    shared_policy: data.shared_policy
  };
  const contextualRequest = JSON.parse(JSON.stringify(currentRequest));
  contextualRequest.messages[0].content = JSON.stringify(evidence, null, 2);
  return {
    case_id: example.case_id,
    original_unsent_request: currentRequest,
    experimental_unsent_request: contextualRequest,
    lookup_input: { system_instructions: currentRequest.system, ...evidence },
    provenance: 'Original builder executed from export; contextual envelope is an offline experiment only'
  };
});
process.stdout.write(JSON.stringify(requests));
"""

CONTROL_DRIVER = r"""
const fs = require('fs');
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
const workflow = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
const wrap = rows => rows.map(json => ({ json }));
function execute(name, rows, lookup) {
  const node = workflow.nodes.find(n => n.name === name);
  return new Function('$input', '$', node.parameters.jsCode)(
    { all: () => wrap(rows) }, lookup || (() => { throw Error('Unexpected lookup'); })
  );
}
const observations = [];
for (const candidate of data.candidates) {
  const normalS = execute('Code (Settlement: normalise + key)', [candidate.row]);
  const normalA = execute('Code (Accrual: normalise + key)', candidate.pools);
  const deterministic = execute('Code (Deterministic Match: one-to-one)', [...normalS, ...normalA].map(i => i.json));
  const unmatched = deterministic.map(i => i.json).filter(j => j._route === 'needs_classification');
  if (unmatched.length !== 1) throw Error('Practical case must contain one unmatched row');
  let proposal;
  if (candidate.decision === 'review') {
    // This is an explicit offline classifier disposition, not a new ledger control.
    proposal = [{ ...unmatched[0], _record_type: 'settlement', _route: 'needs_review',
      _classification_method: candidate.method, _classification_error: 'Comparator requested review before allocation' }];
  } else {
    const built = execute('Code (Build Classification Prompt)', unmatched)[0].json;
    const response = { stop_reason: 'tool_use', content: [{ type: 'tool_use', name: 'submit_classifications',
      input: { classifications: [candidate.answer] } }] };
    proposal = execute('Code (Parse Classification Response)', [response], name => {
      if (name !== 'Code (Build Classification Prompt)') throw Error('Unexpected parser lookup');
      return { first: () => ({ json: built }) };
    }).map(i => ({ ...i.json, _classification_method: candidate.method }));
  }
  const verified = execute('Code (Verify Classification Against Evidence)', proposal, name => {
    if (name !== 'Code (Deterministic Match: one-to-one)') throw Error('Unexpected allocation lookup');
    return { all: () => deterministic };
  });
  observations.push({ case_id: candidate.case_id, method: candidate.method,
    review_requested_before_ledger: candidate.decision === 'review', row: verified[0].json });
}
process.stdout.write(JSON.stringify(observations));
"""


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def prepare(output: Path) -> None:
    if (output / "manifest.json").exists():
        raise FileExistsError("Prepared exercise already exists; do not silently replace frozen inputs")
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node is required for the exported prompt builder")
    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))
    run = subprocess.run(
        [node, "-e", PREPARE_DRIVER, str(WORKFLOW)], input=json.dumps(inputs),
        text=True, capture_output=True, check=True, timeout=30,
    )
    requests = json.loads(run.stdout)
    output.mkdir(parents=True, exist_ok=True)
    parity = []
    for request in requests:
        received = json.loads(request["experimental_unsent_request"]["messages"][0]["content"])
        lookup = request["lookup_input"]
        shared = {key: lookup[key] for key in ("deduction_lines", "guide_sources", "shared_policy")}
        if received != shared:
            raise AssertionError("Evidence differs between request and lookup input")
        if lookup["system_instructions"] != request["experimental_unsent_request"]["system"]:
            raise AssertionError("Category/alias instructions differ")
        parity.append({"case_id": request["case_id"], "same_factual_evidence": True,
                       "evidence_sha256": canonical_hash(shared)})
    observed = {
        "provenance": "AI-authored simulated answers, not model/provider results; preserve unchanged",
        "answers": {case["case_id"]: case["simulated_model_answer"] for case in inputs["cases"]},
    }
    write_json(output / "request_trace.json", requests)
    write_json(output / "observed_answers.json", observed)
    write_json(output / "manifest.json", {
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider_calls": 0, "provider_spend_gbp": 0, "requests_sent": False,
        "inputs_sha256": fingerprint(INPUTS), "expectations_sha256": fingerprint(EXPECTATIONS),
        "workflow_sha256": fingerprint(WORKFLOW),
        "request_trace_sha256": fingerprint(output / "request_trace.json"),
        "observed_answers_sha256": fingerprint(output / "observed_answers.json"),
        "evidence_parity": parity,
        "state": "prepared; predictions required before scoring or expected-answer feedback",
    })
    print(f"Prepared {len(requests)} unsent requests; evidence parity verified for all cases.")
    print("Expected answers withheld; no lookup results or scores produced.")
    print("Provider calls: 0; GBP 0 spent.")


def lookup_decision(evidence: dict) -> dict:
    """Small development lookup; it receives source facts, never expected labels.

    Structured mappings are explicitly present in BOTH the model request and lookup
    input. This function is not a natural-language parser or full V2 replacement.
    """
    row = evidence["deduction_lines"][0]
    mappings = []
    for source in evidence["guide_sources"]:
        if canonical_vendor(source["vendor_name"]) != canonical_vendor(row["vendor_name"]):
            continue
        if source["effective_from"] > row["transaction_date"]:
            continue
        if source.get("effective_to") and source["effective_to"] < row["transaction_date"]:
            continue
        if source["authority"] != "approved":
            continue
        for mapping in source["mappings"]:
            if mapping["reference_code"] == row["reference_code"]:
                mappings.append((mapping["bucket"], source["source_id"]))
    buckets = {bucket for bucket, _ in mappings}
    source_ids = sorted({source_id for _, source_id in mappings})
    if not buckets:
        return {"decision": "abstain", "bucket": None, "source_ids": source_ids}
    if len(buckets) > 1:
        return {"decision": "review", "bucket": None, "source_ids": source_ids}
    return {"decision": "classify", "bucket": next(iter(buckets)), "source_ids": source_ids}


def require_predictions(output: Path, case_ids: set[str]) -> dict:
    path = output / "predictions.json"
    if not path.exists():
        raise ValueError("Predictions must be recorded before scoring")
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = [case_id for case_id in sorted(case_ids)
               if not data.get("predictions", {}).get(case_id, {}).get("response", "").strip()]
    if missing:
        raise ValueError("Predictions still required: " + ", ".join(missing))
    return data


def score(output: Path) -> None:
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))
    case_ids = {case["case_id"] for case in inputs["cases"]}
    predictions = require_predictions(output, case_ids)
    # Only open the expected labels after the prediction guard succeeds.
    for path, key in (
        (INPUTS, "inputs_sha256"), (EXPECTATIONS, "expectations_sha256"),
        (WORKFLOW, "workflow_sha256"), (output / "observed_answers.json", "observed_answers_sha256"),
        (output / "request_trace.json", "request_trace_sha256"),
    ):
        if fingerprint(path) != manifest[key]:
            raise ValueError(f"Frozen material changed: {path.name}")
    expected = json.loads(EXPECTATIONS.read_text(encoding="utf-8"))["cases"]
    observed = json.loads((output / "observed_answers.json").read_text(encoding="utf-8"))["answers"]
    requests = json.loads((output / "request_trace.json").read_text(encoding="utf-8"))
    requests_by_id = {request["case_id"]: request for request in requests}
    lookup_results = {}
    candidates = []
    for case in inputs["cases"]:
        case_id = case["case_id"]
        evidence = requests_by_id[case_id]["lookup_input"]
        # The evidence object used here is the one fingerprinted during preparation.
        received = json.loads(requests_by_id[case_id]["experimental_unsent_request"]["messages"][0]["content"])
        if any(evidence[key] != received[key] for key in ("deduction_lines", "guide_sources", "shared_policy")):
            raise AssertionError("Evidence parity changed")
        decision = lookup_decision(evidence)
        lookup_results[case_id] = decision
        row = {**inputs["common_row"], **case["row"]}
        pools = [{**inputs["common_pool"], **pool} for pool in case["pools"]]
        model_answer = observed[case_id]
        lookup_answer = {"deduction_id": row["deduction_id"], "bucket": decision["bucket"] or "Unresolvable",
                         "confidence": 1.0, "reasoning": "Deterministic guide lookup; " + decision["decision"]}
        for method, answer, disposition in (
            ("simulated_model", model_answer, "abstain" if model_answer["bucket"] == "Unresolvable" else "classify"),
            ("guide_lookup", lookup_answer, decision["decision"]),
        ):
            candidates.append({"case_id": case_id, "method": method, "row": row,
                               "pools": pools, "answer": answer, "decision": disposition})
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node is required for current workflow control replay")
    run = subprocess.run([node, "-e", CONTROL_DRIVER, str(WORKFLOW)],
                         input=json.dumps({"candidates": candidates}), text=True,
                         capture_output=True, check=True, timeout=30)
    routed = {(item["case_id"], item["method"]): item for item in json.loads(run.stdout)}
    results = []
    for case in inputs["cases"]:
        case_id = case["case_id"]
        truth = expected[case_id]
        methods = {}
        for method in ("simulated_model", "guide_lookup"):
            actual = routed[(case_id, method)]
            decision = lookup_results[case_id] if method == "guide_lookup" else {
                "decision": "abstain" if observed[case_id]["bucket"] == "Unresolvable" else "classify",
                "bucket": None if observed[case_id]["bucket"] == "Unresolvable" else observed[case_id]["bucket"],
            }
            correct = (decision["decision"] == truth["expected_decision"]
                       and decision["bucket"] == truth["expected_bucket"])
            expected_route = truth["desired_model_route" if method == "simulated_model" else "desired_lookup_route"]
            methods[method] = {
                "decision": decision, "decision_matches_independent_expectation": correct,
                "desired_route": expected_route, "actual_route": actual["row"]["_route"],
                "routing_matches_independent_expectation": actual["row"]["_route"] == expected_route,
                "review_requested_before_ledger": actual["review_requested_before_ledger"],
                "ledger_forced_review": actual["row"]["_route"] == "needs_review" and not actual["review_requested_before_ledger"],
                "actual_control_row": actual["row"],
            }
        results.append({"case_id": case_id, "independent_expectation": truth,
                        "recorded_user_prediction": predictions["predictions"][case_id],
                        "original_simulated_answer": observed[case_id],
                        "citation_claims": case["citation_claims"],
                        "citation_support_from_fixed_manual_expectation": truth["citation_support"],
                        "methods": methods})
    if fingerprint(output / "observed_answers.json") != manifest["observed_answers_sha256"]:
        raise AssertionError("An observed answer was modified")
    report = {
        "scored_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider_calls": 0, "provider_spend_gbp": 0, "original_answers_unchanged": True,
        "prediction_file_sha256": fingerprint(output / "predictions.json"),
        "script_sha256": fingerprint(Path(__file__)), "results": results,
        "limits": ["Development exercise with AI-authored inputs, mappings, expectations and simulated answers",
                   "Lookup does not read the expected labels; both methods receive the same source facts",
                   "Review from the lookup is its own explicit disposition, passed through a shared offline adapter; it is not detection by the ledger control",
                   "The original provider tool schema lacks explicit review; no production export or control was changed",
                   "Citation-support labels are manually worked from source passages, not an automatic semantic verifier",
                   "No full-run readiness status or real-model performance claim is assessable from this exercise"],
        "model_value_beyond_lookup": "Not demonstrated. Lookup suffices for these three explicit-guide development cases; simulated answers cannot measure real model performance.",
    }
    write_json(output / "comparison_results.json", report)
    print("Predictions recorded for all cases before scoring. Original answers unchanged.")
    print(f"Scored {len(results)} development cases; provider calls 0; GBP 0 spent.")
    print(f"Results: {output / 'comparison_results.json'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=("prepare", "score"), default="prepare")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    (prepare if args.action == "prepare" else score)(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
