"""Preserve raw simulated answers and compare the actual before/after workflow code."""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.practical_comparison import CONTROL_DRIVER

HERE = Path(__file__).parent
PRACTICAL = ROOT / "outputs/practical-2026-10-26"
predictions = json.loads((HERE / "predictions.json").read_text())
assert all(predictions["predictions"][key]["response"].strip() for key in ("P1", "P3"))
manifest = json.loads((PRACTICAL / "manifest.json").read_text())
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert digest(HERE / "before_workflow.json") == manifest["workflow_sha256"]
assert digest(PRACTICAL / "observed_answers.json") == manifest["observed_answers_sha256"]
assert digest(ROOT / "fixtures/development/practical_inputs.json") == manifest["inputs_sha256"]
assert digest(ROOT / "fixtures/development/practical_expectations.json") == manifest["expectations_sha256"]
inputs = json.loads((ROOT / "fixtures/development/practical_inputs.json").read_text())
observed = json.loads((PRACTICAL / "observed_answers.json").read_text())["answers"]
expectations = json.loads((ROOT / "fixtures/development/practical_expectations.json").read_text())["cases"]
candidates = []
for case in inputs["cases"]:
    if case["case_id"] not in ("P1", "P3"):
        continue
    candidates.append({
        "case_id": case["case_id"], "method": "simulated_model", "decision": "classify",
        "row": {**inputs["common_row"], **case["row"]},
        "pools": [{**inputs["common_pool"], **pool} for pool in case["pools"]],
        "answer": observed[case["case_id"]],
    })
versions = {}
for label, workflow in (("before", HERE / "before_workflow.json"),
                        ("after", ROOT / "workflows/DEDUCTION_RESOLUTION_WORKBENCH_V2.json")):
    run = subprocess.run(["node", "-e", CONTROL_DRIVER, str(workflow)],
                         input=json.dumps({"candidates": candidates}), text=True,
                         capture_output=True, check=True, timeout=30)
    versions[label] = {item["case_id"]: item["row"] for item in json.loads(run.stdout)}
results = []
for case in inputs["cases"]:
    case_id = case["case_id"]
    if case_id not in ("P1", "P3"):
        continue
    before, after = versions["before"][case_id], versions["after"][case_id]
    assert before["_route"] == "classified_verified"
    assert after["_route"] == expectations[case_id]["desired_model_route"]
    assert after["llm_bucket"] == observed[case_id]["bucket"]
    assert after["llm_reasoning"] == observed[case_id]["reasoning"]
    assert after["llm_confidence"] == observed[case_id]["confidence"]
    assert not any(key in after for key in ("_allocated_amount", "_evidence_balance_before", "_evidence_balance_after"))
    results.append({
        "case_id": case_id, "original_answer_unchanged": observed[case_id],
        "model_decision_still_incorrect": True,
        "citation_supported": expectations[case_id]["citation_support"],
        "reviewer_source_context": case["sources"],
        "before": before, "after": after,
        "allocated_before_gbp": before["_allocated_amount"], "allocated_after_gbp": 0,
        "routing_corrected_without_correcting_model_answer": True,
    })
assert digest(PRACTICAL / "observed_answers.json") == manifest["observed_answers_sha256"]
report = {
    "verified_at_utc": datetime.now(timezone.utc).isoformat(),
    "provider_calls": 0, "provider_spend_gbp": 0,
    "before_workflow_sha256": digest(HERE / "before_workflow.json"),
    "after_workflow_sha256": digest(ROOT / "workflows/DEDUCTION_RESOLUTION_WORKBENCH_V2.json"),
    "original_answers_sha256": digest(PRACTICAL / "observed_answers.json"),
    "prediction_sha256": digest(HERE / "predictions.json"),
    "results": results,
    "limits": ["Both answers are simulated; no model accuracy improvement is claimed",
               "Workflow stops unconfigured categories conservatively; it does not ingest or semantically verify guide text",
               "Reviewer guides are retained in this local development evidence bundle, not newly connected to n8n",
               "Later guide-based classification/correction and allocation require a separate authorised decision"],
}
(HERE / "before_after_results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print("Both preserved simulated answers: accepted before, review after; no allocation after.")
print("Wrong model answers remain wrong; review routing is corrected separately.")
print("Provider calls 0; GBP 0 spent.")
