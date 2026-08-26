import csv
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.deduction_rules import canonical_vendor
from scripts.finalize_run import BRANCH_FILES, finalize


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "workflows" / "DEDUCTION_RESOLUTION_WORKBENCH_V2.json"


class WorkflowV2Tests(unittest.TestCase):
    def test_workflow_allocates_after_all_llm_batches_finish(self):
        workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
        connections = workflow["connections"]
        self.assertEqual(
            connections["Code (Parse Classification Response)"]["main"][0][0]["node"],
            "Loop Over Unmatched Lines",
        )
        self.assertEqual(
            connections["Loop Over Unmatched Lines"]["main"][0][0]["node"],
            "Code (Verify Classification Against Evidence)",
        )
        self.assertEqual(
            connections["Code (Verify Classification Against Evidence)"]["main"][0][0]["node"],
            "Route Classification Results",
        )

    def test_workflow_contains_versioned_alias_and_balance_controls(self):
        workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
        code = "\n".join(
            node["parameters"]["jsCode"] for node in workflow["nodes"]
            if node["type"] == "n8n-nodes-base.code"
        )
        self.assertIn("RULESET_VERSION = '2.0.0'", code)
        self.assertIn("return 'amazon'", code)
        self.assertIn("programme_pool", code)
        self.assertIn("_available_cents", code)
        self.assertIn("OTHER-DEDUCT-", code)
        self.assertIn("_classification_method", code)
        self.assertIn("same-vendor exact-amount near-date candidate", code)
        self.assertIn(
            "vendorScore(j._normalised_vendor, a._normalised_vendor) >= 60",
            code,
        )
        self.assertNotIn("AMOUNT_BAND_MULTIPLIER", code)
        self.assertIn("validUtcDate", code)
        self.assertIn("invalid_calendar_date", code)
        self.assertIn("Number.isFinite(dateDelta)", code)
        self.assertIn("accrual_id values must be present and unique", code)
        self.assertIn("/^[+-]?", code)
        self.assertNotIn("parseFloat", code)

    def _execute_normaliser(self, node_name, rows):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for the embedded JavaScript runtime test")
        driver = r"""
const fs = require('fs');
const workflow = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
const nodeName = process.argv[2];
const rows = JSON.parse(fs.readFileSync(0, 'utf8'));
const code = workflow.nodes.find(n => n.name === nodeName).parameters.jsCode;
try {
  const result = new Function('$input', code)({ all: () => rows.map(json => ({ json })) });
  process.stdout.write(JSON.stringify({ ok: true, rows: result.map(item => item.json) }));
} catch (error) {
  process.stdout.write(JSON.stringify({ ok: false, error: error.message }));
}
"""
        completed = subprocess.run(
            [node, "-e", driver, str(WORKFLOW), node_name],
            input=json.dumps(rows), text=True, capture_output=True, check=True,
        )
        return json.loads(completed.stdout)

    def test_embedded_settlement_parser_rejects_malformed_values(self):
        rows = [
            {"deduction_id": "D1", "transaction_date": "2026-02-31", "amount": "100.00", "vendor_name": "Amazon"},
            {"deduction_id": "D2", "transaction_date": "2026-08-25", "amount": "100GBP", "vendor_name": "Amazon"},
            {"deduction_id": "D3", "transaction_date": "2026-08-25", "amount": "-100.00", "vendor_name": "Amazon"},
            {"deduction_id": "D4", "transaction_date": "2026-08-25", "amount": "0", "vendor_name": "Amazon"},
            {"deduction_id": "D5", "transaction_date": "2026-02-29", "amount": "100.00", "vendor_name": "Amazon"},
            {"deduction_id": "D6", "transaction_date": "2024-02-29", "amount": "100.00", "vendor_name": "Amazon"},
        ]
        result = self._execute_normaliser("Code (Settlement: normalise + key)", rows)
        self.assertTrue(result["ok"])
        by_id = {row["deduction_id"]: row for row in result["rows"]}
        self.assertEqual(by_id["D1"]["error"], "invalid_calendar_date")
        self.assertEqual(by_id["D2"]["error"], "invalid_amount")
        self.assertTrue(by_id["D3"]["matchable"])
        self.assertEqual(by_id["D4"]["error"], "invalid_amount")
        self.assertEqual(by_id["D5"]["error"], "invalid_calendar_date")
        self.assertTrue(by_id["D6"]["matchable"])

    def test_embedded_accrual_parser_stops_on_duplicate_ids(self):
        rows = [
            {"accrual_id": "A1", "accrual_date": "2026-08-25", "amount": "100.00", "vendor_name": "Amazon"},
            {"accrual_id": "A1", "accrual_date": "2026-08-25", "amount": "50.00", "vendor_name": "Amazon"},
        ]
        result = self._execute_normaliser("Code (Accrual: normalise + key)", rows)
        self.assertFalse(result["ok"])
        self.assertIn("present and unique", result["error"])

    def test_embedded_vendor_aliases_match_the_python_rules(self):
        names = [
            "AMZN Mktp UK", "Amazon EU SARL", "AMAZON.COM LLC",
            "WALMART.COM", "Target Stores", "Costco Wholesale",
            "Shopify Payments", "Unknown Remitter", "Amazonian Retail",
            "MKTPL-SETTLEMENT-EU",
        ]
        rows = [
            {
                "deduction_id": f"D{index}",
                "transaction_date": "2026-08-25",
                "amount": "100.00",
                "vendor_name": name,
            }
            for index, name in enumerate(names, 1)
        ]
        result = self._execute_normaliser("Code (Settlement: normalise + key)", rows)
        self.assertTrue(result["ok"])
        actual = [row["_normalised_vendor"] for row in result["rows"]]
        self.assertEqual(actual, [canonical_vendor(name) for name in names])

    def test_public_workflow_export_is_inactive_and_portable(self):
        workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
        self.assertFalse(workflow["active"])
        self.assertFalse(workflow["settings"]["availableInMCP"])
        self.assertNotIn("id", workflow)
        self.assertNotIn("versionId", workflow)
        self.assertNotIn("instanceId", workflow.get("meta", {}))
        credential_refs = [
            credential
            for node in workflow["nodes"]
            for credential in node.get("credentials", {}).values()
        ]
        self.assertTrue(credential_refs)
        self.assertTrue(all(ref["id"] == "REPLACE_WITH_N8N_CREDENTIAL_ID" for ref in credential_refs))

    def test_workflow_always_exports_all_five_branches(self):
        workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
        export_node = next(
            node for node in workflow["nodes"]
            if node["name"] == "Code (Build Complete Branch Exports)"
        )
        code = export_node["parameters"]["jsCode"]
        for filename in BRANCH_FILES:
            self.assertIn(filename, code)
        verify_targets = {
            target["node"]
            for target in workflow["connections"]
            ["Code (Verify Classification Against Evidence)"]["main"][0]
        }
        self.assertIn("Code (Build Complete Branch Exports)", verify_targets)
        self.assertEqual(
            workflow["connections"]["Code (Build Complete Branch Exports)"]
            ["main"][0][0]["node"],
            "Write Complete Branch Exports",
        )

    def test_finalize_only_materialises_empty_files_after_exact_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outputs = root / "outputs"
            outputs.mkdir()
            settlements = root / "settlements.csv"
            with settlements.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["deduction_id"])
                writer.writeheader()
                writer.writerows([{"deduction_id": "D1"}, {"deduction_id": "D2"}])
            (outputs / "auto_matched.json").write_text(
                json.dumps([{"deduction_id": "D1"}, {"deduction_id": "D2"}]), encoding="utf-8"
            )
            manifest = finalize(outputs, settlements)
            self.assertEqual(manifest["input_lines"], 2)
            for filename in BRANCH_FILES:
                self.assertTrue((outputs / filename).exists())

    def test_finalize_refuses_to_hide_an_omitted_line(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outputs = root / "outputs"
            outputs.mkdir()
            settlements = root / "settlements.csv"
            settlements.write_text("deduction_id\nD1\nD2\n", encoding="utf-8")
            (outputs / "auto_matched.json").write_text('[{"deduction_id":"D1"}]', encoding="utf-8")
            with self.assertRaises(ValueError):
                finalize(outputs, settlements)


if __name__ == "__main__":
    unittest.main()
