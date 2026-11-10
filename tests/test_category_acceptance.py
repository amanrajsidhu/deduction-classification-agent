"""Category authority must be established before programme-balance allocation."""

import copy
import hashlib
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from scripts.deduction_rules import allocate_evidence
from scripts.generate_xlsx_output import (
    compute_metrics, load_answer_key, load_run_outputs, load_source_accruals, record_value,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "workflows/DEDUCTION_RESOLUTION_WORKBENCH_V2.json"
INPUTS = ROOT / "fixtures/development/practical_inputs.json"

DRIVER = r"""
const fs = require('fs');
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
const workflow = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
function execute(name, rows, lookup) {
  const node = workflow.nodes.find(n => n.name === name);
  return new Function('$input', '$', node.parameters.jsCode)(
    { all: () => rows.map(json => ({ json })) }, lookup
  );
}
const settlements = execute('Code (Settlement: normalise + key)', data.rows)
  .map(i => ({ ...i.json, _record_type: 'settlement', _route: i.json._route || 'pending_verification' }));
const accruals = execute('Code (Accrual: normalise + key)', data.accruals)
  .map(i => ({ json: { ...i.json, _record_type: 'accrual' } }));
const result = execute('Code (Verify Classification Against Evidence)', settlements, name => {
  if (name !== 'Code (Deterministic Match: one-to-one)') throw Error('Unexpected lookup');
  return { all: () => accruals };
});
process.stdout.write(JSON.stringify(result.map(i => i.json)));
"""


class CategoryAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        cls.inputs = json.loads(INPUTS.read_text(encoding="utf-8"))

    def run_exported(self, rows, accruals):
        if not self.node:
            self.skipTest("Node is required for delivered workflow-code checks")
        result = subprocess.run(
            [self.node, "-e", DRIVER, str(WORKFLOW)],
            input=json.dumps({"rows": rows, "accruals": accruals}),
            text=True, capture_output=True, check=True, timeout=15,
        )
        return json.loads(result.stdout)

    def case(self, case_id):
        case = next(item for item in self.inputs["cases"] if item["case_id"] == case_id)
        answer = case["simulated_model_answer"]
        row = {
            **self.inputs["common_row"], **case["row"],
            "llm_bucket": answer["bucket"], "llm_confidence": answer["confidence"],
            "llm_reasoning": answer["reasoning"], "_classification_method": "ai_proposal",
        }
        pools = [{**self.inputs["common_pool"], **pool} for pool in case["pools"]]
        return row, pools

    def assert_rejected_without_rewriting(self, original, actual):
        self.assertEqual(actual["_route"], "needs_review")
        self.assertEqual(actual["llm_bucket"], original["llm_bucket"])
        self.assertEqual(actual["llm_reasoning"], original["llm_reasoning"])
        self.assertEqual(actual["llm_confidence"], original["llm_confidence"])
        for field in ("_evidence_accrual_id", "_allocated_amount", "_evidence_balance_before", "_evidence_balance_after"):
            self.assertNotIn(field, actual)

    def test_proposal_contradicting_guidance_cannot_pass_on_balance_alone(self):
        row, pools = self.case("P1")
        self.assert_rejected_without_rewriting(row, self.run_exported([row], pools)[0])

    def test_choice_between_conflicting_guides_cannot_pass_on_balance_alone(self):
        row, pools = self.case("P3")
        self.assert_rejected_without_rewriting(row, self.run_exported([row], pools)[0])

    def test_rejected_proposal_cannot_consume_balance_before_a_supported_row(self):
        rejected, pools = self.case("P1")
        # Forged provenance must not substitute for a raw-reference authority check.
        rejected["_classification_method"] = "configured_alias"
        supported = {**rejected, "deduction_id": "FOLLOWUP", "amount": "60.00",
                     "reference_code": "PRC-DISP-SUPPORTED", "llm_reasoning": "Configured test case"}
        for runner in (self.run_exported, allocate_evidence):
            with self.subTest(runner=runner.__name__):
                rows = runner(copy.deepcopy([rejected, supported]), copy.deepcopy(pools))
                self.assert_rejected_without_rewriting(rejected, rows[0])
                self.assertEqual(rows[1]["_route"], "classified_verified")
                self.assertEqual(rows[1]["_evidence_balance_before"], 500.0)
                self.assertEqual(rows[1]["_evidence_balance_after"], 440.0)

    def test_python_reference_rejects_the_same_two_unsupported_proposals(self):
        for case_id in ("P1", "P3"):
            with self.subTest(case=case_id):
                row, pools = self.case(case_id)
                self.assert_rejected_without_rewriting(row, allocate_evidence([row], pools)[0])

    def test_correct_but_unconfigured_proposal_also_requires_review(self):
        row, pools = self.case("P1")
        row["llm_bucket"] = "Shortage Claim"
        for runner in (self.run_exported, allocate_evidence):
            with self.subTest(runner=runner.__name__):
                self.assert_rejected_without_rewriting(row, runner([row], pools)[0])

    def test_configured_reference_must_agree_with_category_at_boundary(self):
        row, pools = self.case("P1")
        row["reference_code"] = "SHORT-CONFIGURED"
        # Price Dispute still has an eligible balance, but contradicts the configuration.
        for runner in (self.run_exported, allocate_evidence):
            with self.subTest(runner=runner.__name__):
                self.assert_rejected_without_rewriting(row, runner([row], pools)[0])

    def test_configured_category_still_requires_sufficient_eligible_balance(self):
        row, pools = self.case("P1")
        row.update(reference_code="SHORT-CONFIGURED", llm_bucket="Shortage Claim")
        for runner in (self.run_exported, allocate_evidence):
            with self.subTest(runner=runner.__name__):
                accepted = runner([row], pools)[0]
                self.assertEqual(accepted["_route"], "classified_verified")
                self.assertEqual(accepted["_evidence_balance_after"], 410.0)
                underfunded = [{**pool, "amount": "80.00"} for pool in pools]
                stopped = runner([row], underfunded)[0]
                self.assertEqual(stopped["_route"], "needs_review")
                self.assertNotIn("_allocated_amount", stopped)

    def test_original_simulated_answers_remain_unchanged(self):
        before = hashlib.sha256(INPUTS.read_bytes()).hexdigest()
        original = copy.deepcopy(self.inputs)
        for case_id in ("P1", "P3"):
            row, pools = self.case(case_id)
            self.run_exported([row], pools)
        self.assertEqual(hashlib.sha256(INPUTS.read_bytes()).hexdigest(), before)
        self.assertEqual(self.inputs, original)

    def test_evaluator_separates_category_authority_from_valid_ledger_allocation(self):
        outputs, problems = load_run_outputs(ROOT / "outputs/v2")
        _, truth = load_answer_key(ROOT / "fixtures/v2/answer_key.json.gz")
        accruals, source_problems = load_source_accruals(ROOT / "fixtures/v2/invoice_accruals.csv")
        original = compute_metrics(outputs, truth, problems, accruals, source_problems)
        changed = copy.deepcopy(outputs)
        row = changed["classified_verified"][0]
        row["reference_code"] = "RX-UNCONFIGURED"
        row["_classification_method"] = "configured_alias"  # Forged provenance is insufficient.
        metrics = compute_metrics(changed, truth, problems, accruals, source_problems)
        self.assertTrue(metrics["source_allocation_integrity"])
        self.assertEqual(metrics["classification_precision"], 1.0)
        self.assertFalse(metrics["category_evidence_integrity"])
        self.assertIn(row["deduction_id"], metrics["invalid_category_evidence_ids"])
        self.assertNotIn(row["deduction_id"], metrics["valid_accepted_evidence_ids"])
        self.assertEqual(metrics["overall_status"], "Needs Repair")
        self.assertAlmostEqual(metrics["resolved_value_gbp"], original["resolved_value_gbp"] - record_value(row))
        self.assertEqual(metrics["allocated_classified_value_gbp"], original["allocated_classified_value_gbp"])

    def test_existing_review_stop_is_not_reopened_by_configuration_or_balance(self):
        row, pools = self.case("P1")
        row.update(reference_code="SHORT-CONFIGURED", llm_bucket="Shortage Claim",
                   _route="needs_review", _classification_error="Prior review decision")
        for runner in (self.run_exported, allocate_evidence):
            with self.subTest(runner=runner.__name__):
                actual = runner([row], pools)[0]
                self.assert_rejected_without_rewriting(row, actual)
                self.assertEqual(actual["_classification_error"], "Prior review decision")


if __name__ == "__main__":
    unittest.main()
