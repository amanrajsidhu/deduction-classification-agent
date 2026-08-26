import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from scripts.deduction_rules import allocate_evidence, days_between, to_cents, vendor_score
from scripts.generate_dataset import generate
from scripts.generate_xlsx_output import (
    compute_metrics,
    load_answer_key,
    load_run_outputs,
    load_source_accruals,
)

ROOT = Path(__file__).resolve().parents[1]


def read_csv(path):
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_answer_key(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


class V2RuleTests(unittest.TestCase):
    def test_known_vendor_aliases_share_one_identity(self):
        self.assertEqual(vendor_score("AMZN Mktp UK", "Amazon"), 100)
        self.assertEqual(vendor_score("Amazon EU SARL", "AMAZON.COM LLC"), 100)
        self.assertEqual(vendor_score("WALMART.COM", "Walmart"), 100)
        self.assertEqual(vendor_score("Unknown Remitter", "Amazon"), 0)
        self.assertEqual(vendor_score("MKTPL-SETTLEMENT-EU", "Amazon"), 0)

    def test_fixture_is_byte_reproducible(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            paths_a = generate(Path(first))
            paths_b = generate(Path(second))
            for key in paths_a:
                self.assertEqual(paths_a[key].read_bytes(), paths_b[key].read_bytes(), key)
            for key in ("settlements", "accruals"):
                self.assertNotIn(b"\r\n", paths_a[key].read_bytes(), key)

    def test_v2_fixture_has_matchable_pairs_and_no_accidental_classifiable_match(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = generate(Path(directory))
            settlements = {row["deduction_id"]: row for row in read_csv(paths["settlements"])}
            accruals = read_csv(paths["accruals"])
            accrual_by_id = {row["accrual_id"]: row for row in accruals}
            answer = read_answer_key(paths["answer_key"])
            for entry in answer["entries"]:
                row = settlements[entry["deduction_id"]]
                if entry["seed_category"] == "auto_matched":
                    accrual = accrual_by_id[entry["matched_accrual_id"]]
                    self.assertLessEqual(abs(to_cents(row["amount"]) - to_cents(accrual["amount"])), 1)
                    self.assertLessEqual(days_between(row["transaction_date"], accrual["accrual_date"]), 1)
                    self.assertGreaterEqual(vendor_score(row["vendor_name"], accrual["vendor_name"]), 60)
                elif entry["seed_category"] == "classifiable":
                    accidental = [
                        accrual for accrual in accruals
                        if abs(to_cents(row["amount"]) - to_cents(accrual["amount"])) <= 1
                        and days_between(row["transaction_date"], accrual["accrual_date"]) <= 1
                        and vendor_score(row["vendor_name"], accrual["vendor_name"]) >= 60
                    ]
                    self.assertEqual(accidental, [], row["deduction_id"])

    def test_one_full_run_allocation_never_reuses_exhausted_balance(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = generate(Path(directory))
            settlements = {row["deduction_id"]: row for row in read_csv(paths["settlements"])}
            accruals = read_csv(paths["accruals"])
            answer = read_answer_key(paths["answer_key"])
            classifications = []
            for entry in answer["entries"]:
                if entry["seed_category"] == "auto_matched":
                    continue
                row = settlements[entry["deduction_id"]]
                classifications.append({
                    **row,
                    "llm_bucket": entry["true_bucket"] or "Unresolvable",
                    "llm_confidence": 1.0,
                    "llm_reasoning": "Synthetic control-path fixture",
                })
            routed = allocate_evidence(classifications, accruals)
            classifiable = [row for row in routed if row["llm_bucket"] != "Unresolvable"]
            unresolvable = [row for row in routed if row["llm_bucket"] == "Unresolvable"]
            self.assertEqual(len(classifiable), 75)
            self.assertTrue(all(row["_route"] == "classified_verified" for row in classifiable))
            self.assertTrue(all(row["_evidence_balance_after"] >= 0 for row in classifiable))
            self.assertEqual(len(unresolvable), 25)
            self.assertTrue(all(row["_route"] == "unresolvable" for row in unresolvable))

            entries = {entry["deduction_id"]: entry for entry in answer["entries"]}
            auto_rows = [
                {
                    **settlements[entry["deduction_id"]],
                    "matched_accrual_id": entry["matched_accrual_id"],
                    "matched_bucket": entry["true_bucket"],
                }
                for entry in answer["entries"] if entry["seed_category"] == "auto_matched"
            ]
            metrics = compute_metrics({
                "auto_matched": auto_rows,
                "classified_verified": classifiable,
                "needs_review": [],
                "unresolvable": unresolvable,
                "data_quality_issue": [],
            }, entries, [], accruals, [])
            self.assertEqual(metrics["overall_status"], "Ready for Demo")
            self.assertEqual(metrics["terminal_misroute_count"], 0)
            self.assertEqual(metrics["evidence_allocation_coverage"], 1.0)
            self.assertTrue(metrics["source_allocation_integrity"])

    def test_duplicate_or_blank_accrual_identity_stops_allocation(self):
        accrual = {
            "accrual_id": "A1", "amount": "100.00", "evidence_scope": "programme_pool",
            "bucket": "Promotional Accrual", "vendor_name": "Amazon", "accrual_date": "2026-08-25",
        }
        with self.assertRaisesRegex(ValueError, "present and unique"):
            allocate_evidence([], [accrual, dict(accrual)])
        with self.assertRaisesRegex(ValueError, "present and unique"):
            allocate_evidence([], [{**accrual, "accrual_id": ""}])

    def test_unresolvable_conflict_requires_same_vendor(self):
        classification = [{
            "deduction_id": "D1", "amount": "100.00", "transaction_date": "2026-08-25",
            "vendor_name": "Amazon", "llm_bucket": "Unresolvable",
        }]
        base_accrual = {
            "accrual_id": "A1", "amount": "100.00", "accrual_date": "2026-08-25",
            "vendor_name": "Walmart", "evidence_scope": "transaction_match", "bucket": "Chargeback/Other",
        }
        self.assertEqual(allocate_evidence(classification, [base_accrual])[0]["_route"], "unresolvable")
        same_vendor = [{**base_accrual, "vendor_name": "Amazon"}]
        self.assertEqual(allocate_evidence(classification, same_vendor)[0]["_route"], "needs_review")

    def test_committed_v2_outputs_pass_the_source_bound_evaluator(self):
        outputs, problems = load_run_outputs(ROOT / "outputs" / "v2")
        _counts, entries = load_answer_key(ROOT / "fixtures" / "v2" / "answer_key.json.gz")
        accruals, accrual_problems = load_source_accruals(
            ROOT / "fixtures" / "v2" / "invoice_accruals.csv"
        )
        metrics = compute_metrics(outputs, entries, problems, accruals, accrual_problems)
        self.assertEqual(metrics["overall_status"], "Ready for Demo")
        self.assertTrue(metrics["source_allocation_integrity"])
        self.assertEqual(metrics["terminal_misroute_count"], 0)


if __name__ == "__main__":
    unittest.main()
