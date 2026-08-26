"""Materialise explicit empty branch files only after routing coverage is proven."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:
    from .deduction_rules import RULESET_VERSION
except ImportError:
    from deduction_rules import RULESET_VERSION

BRANCH_FILES = [
    "auto_matched.json", "classified_verified.json", "needs_review.json",
    "unresolvable.json", "data_quality_issues.json",
]


def settlement_ids(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [row["deduction_id"] for row in csv.DictReader(handle)]


def load_existing_ids(outputs_dir: Path):
    routed, counts, missing = [], {}, []
    for filename in BRANCH_FILES:
        path = outputs_dir / filename
        if not path.exists():
            missing.append(filename)
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ValueError(f"{filename} must contain a JSON array")
        ids = [str(row.get("deduction_id")) for row in data]
        routed.extend(ids)
        counts[filename] = len(ids)
    return routed, counts, missing


def finalize(outputs_dir: Path, settlement_csv: Path) -> dict:
    outputs_dir.mkdir(parents=True, exist_ok=True)
    expected = settlement_ids(settlement_csv)
    routed, counts, missing = load_existing_ids(outputs_dir)
    duplicate_ids = sorted(key for key, count in Counter(routed).items() if count > 1)
    unknown_ids = sorted(set(routed) - set(expected))
    omitted_ids = sorted(set(expected) - set(routed))
    if duplicate_ids or unknown_ids or omitted_ids:
        raise ValueError(
            "Cannot materialise empty branches until coverage is exact: "
            f"duplicates={len(duplicate_ids)}, unknown={len(unknown_ids)}, omitted={len(omitted_ids)}"
        )
    for filename in missing:
        (outputs_dir / filename).write_text("[]\n", encoding="utf-8")
        counts[filename] = 0
    manifest = {
        "status": "complete", "ruleset_version": RULESET_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_lines": len(expected), "branch_counts": counts,
        "materialised_empty_branches": missing,
    }
    (outputs_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs-dir", type=Path, default=root / "outputs" / "v2")
    parser.add_argument("--settlement-csv", type=Path, default=root / "fixtures" / "v2" / "settlement_deductions.csv")
    args = parser.parse_args()
    print(json.dumps(finalize(args.outputs_dir, args.settlement_csv), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
