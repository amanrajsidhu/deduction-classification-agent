"""Replay the unchanged 250 saved proposals through the corrected local export."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.feasibility_checkpoint import DRIVER, read_csv
from scripts.generate_xlsx_output import load_run_outputs

saved, problems = load_run_outputs(ROOT / "outputs/v2")
assert not problems
payload = {
    "settlements": read_csv(ROOT / "fixtures/v2/settlement_deductions.csv"),
    "accruals": read_csv(ROOT / "fixtures/v2/invoice_accruals.csv"),
    "proposals": saved["classified_verified"] + saved["unresolvable"] + saved["needs_review"],
    "development": {"cases": []},
}
run = subprocess.run(["node", "-e", DRIVER, str(ROOT / "workflows/DEDUCTION_RESOLUTION_WORKBENCH_V2.json")],
                     input=json.dumps(payload), text=True, capture_output=True, check=True, timeout=30)
result = json.loads(run.stdout)["baseline"]
target = Path(__file__).parent / "baseline_replay"
target.mkdir(exist_ok=True)
for name, rows in result["branches"].items():
    (target / name).write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
print("Corrected workflow baseline replay completed without provider calls.")
