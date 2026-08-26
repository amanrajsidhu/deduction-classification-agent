"""Generate the reproducible V2 synthetic deduction fixture.

V2 separates one-to-one transaction accruals from programme-level evidence
balances. Classifiable deductions can therefore be allocated to a real balance
without reusing one arbitrary leftover accrual as unlimited "proof".
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

try:
    from .deduction_rules import RULESET_VERSION, vendor_score
except ImportError:  # direct script execution
    from deduction_rules import RULESET_VERSION, vendor_score

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = PROJECT_ROOT / "fixtures" / "v2"
SEED = 42
CURRENCY = "GBP"
PERIOD_START = date(2026, 6, 1)
PERIOD_END = date(2026, 6, 30)

BUCKETS = [
    "Promotional Accrual", "Shortage Claim", "Price Dispute",
    "Damaged Goods", "Chargeback/Other",
]
AMOUNT_RANGES = {
    "Promotional Accrual": (500.00, 3200.00),
    "Shortage Claim": (60.00, 420.00),
    "Price Dispute": (25.00, 310.00),
    "Damaged Goods": (35.00, 540.00),
    "Chargeback/Other": (15.00, 980.00),
}
CHANNELS = {
    "Amazon": ["Amazon EU SARL", "AMAZON.COM LLC", "Amazon Services Europe", "AMZN Mktp UK", "Amazon EU Sarl - UK Branch"],
    "Walmart": ["Walmart Inc", "WALMART.COM", "Walmart Marketplace LLC"],
    "Target": ["Target Corporation", "TARGET.COM", "Target Plus Marketplace"],
    "Costco": ["Costco Wholesale Corp", "COSTCO.COM", "Costco Marketplace"],
    "Shopify Direct": ["Shopify Payments", "SHOPIFY INC", "Shopify Direct Sales"],
}
GENERIC_REFERENCES = ["ADJ-{n}", "DED-{n}", "REF-{n}", "SETTLEMENT-{n}", "NOTE-{n}"]
HINT_REFERENCES = {
    "Promotional Accrual": ["PROMO-{n}", "MKTG-REBATE-{n}", "TRADE-PROMO-{n}"],
    "Shortage Claim": ["SHORT-{n}", "QTY-SHORT-{n}", "MISSING-UNITS-{n}"],
    "Price Dispute": ["PRC-DISP-{n}", "PRICE-ADJ-{n}", "PPD-{n}"],
    "Damaged Goods": ["DMG-CLAIM-{n}", "DAMAGED-RMA-{n}", "WHSE-DMG-{n}"],
    "Chargeback/Other": ["CHB-{n}", "MISC-ADJ-{n}", "OTHER-DEDUCT-{n}"],
}
GENERIC_DESCRIPTIONS = [
    "Reimbursement adjustment - see portal", "Deduction per remittance advice",
    "Account adjustment - refer to statement", "Miscellaneous deduction - see note",
    "Adjustment applied at settlement",
]
HINT_DESCRIPTIONS = {
    "Promotional Accrual": ["Aggregated promo rebate - multiple campaigns", "Trade promotion funding adjustment", "Marketing rebate accrual drawdown"],
    "Shortage Claim": ["Aggregated shortage adjustment - multiple SKUs", "Inventory receipt shortfall claim", "Units short on receipt - claim filed"],
    "Price Dispute": ["Retroactive price adjustment - multiple POs", "Cost price discrepancy claim", "Price protection dispute adjustment"],
    "Damaged Goods": ["Warehouse damage claim - multiple units", "Inbound damage adjustment", "Damaged inventory write-down claim"],
    "Chargeback/Other": ["Aggregated chargeback - see case file", "Miscellaneous marketplace deduction", "Other adjustment - multiple references"],
}
UNRESOLVABLE_VENDORS = [
    "Marketplace Services Ltd", "3rd Party Payment Processor",
    "Unknown Remitter", "Payments Clearing House",
]
UNRESOLVABLE_DESCRIPTIONS = [
    "Account adjustment - see remittance advice", "Miscellaneous deduction - refer to portal",
    "Balance adjustment - no further detail", "General ledger adjustment",
]


class Generator:
    def __init__(self, seed: int = SEED):
        self.random = random.Random(seed)
        self.counter = 0
        self.seed = seed

    def next_number(self) -> int:
        self.counter += 1
        return self.counter

    def random_date(self) -> date:
        return PERIOD_START + timedelta(days=self.random.randint(0, (PERIOD_END - PERIOD_START).days))

    def random_amount(self, bucket: str) -> float:
        low, high = AMOUNT_RANGES[bucket]
        return round(self.random.uniform(low, high), 2)

    def vendor_variant(self, channel: str) -> str:
        variant = self.random.choice(CHANNELS[channel])
        assert vendor_score(variant, channel) >= 60
        return variant

    def transaction_accruals(self):
        rows, by_bucket = [], {bucket: [] for bucket in BUCKETS}
        for bucket in BUCKETS:
            for _ in range(30):
                channel = self.random.choice(list(CHANNELS))
                row = {
                    "accrual_id": f"ACR-2026-{self.next_number():05d}",
                    "accrual_date": self.random_date().isoformat(),
                    "accrual_period": "2026-06",
                    "vendor_name": channel,
                    "bucket": bucket,
                    "amount": self.random_amount(bucket),
                    "currency": CURRENCY,
                    "reference_code": f"SAP-TXN-{self.next_number():04d}",
                    "description": f"{bucket} - transaction accrual",
                    "evidence_scope": "transaction_match",
                }
                rows.append(row)
                by_bucket[bucket].append(row)
        return rows, by_bucket

    def matchable_rows(self, accruals):
        rows, answers = [], []
        for accrual in accruals:
            settlement_date = date.fromisoformat(accrual["accrual_date"]) + timedelta(days=self.random.choice([-1, 0, 1]))
            amount = round(accrual["amount"] + self.random.choice([0, 0, 0, 0.01, -0.01]), 2)
            deduction_id = f"DED-2026-{self.next_number():05d}"
            rows.append({
                "deduction_id": deduction_id,
                "transaction_date": settlement_date.isoformat(),
                "vendor_name": self.vendor_variant(accrual["vendor_name"]),
                "amount": -abs(amount), "currency": CURRENCY,
                "reference_code": self.random.choice(GENERIC_REFERENCES).format(n=self.next_number()),
                "description": self.random.choice(GENERIC_DESCRIPTIONS),
            })
            answers.append({
                "deduction_id": deduction_id, "seed_category": "auto_matched",
                "true_bucket": accrual["bucket"], "matched_accrual_id": accrual["accrual_id"],
                "supporting_accrual_id": accrual["accrual_id"],
                "notes": "amount/date/vendor match to a dedicated transaction accrual",
            })
        return rows, answers

    def classifiable_rows(self):
        rows, answers = [], []
        grouped = defaultdict(list)
        for bucket in BUCKETS:
            for index in range(15):
                channel = self.random.choice(list(CHANNELS))
                amount = self.random_amount(bucket)
                # A non-round offset prevents accidental exact matching to the
                # transaction accrual population while preserving realistic value.
                amount = round(amount + (0.37 if index % 2 == 0 else -0.23), 2)
                settlement_date = self.random_date()
                deduction_id = f"DED-2026-{self.next_number():05d}"
                row = {
                    "deduction_id": deduction_id,
                    "transaction_date": settlement_date.isoformat(),
                    "vendor_name": self.vendor_variant(channel),
                    "amount": -abs(amount), "currency": CURRENCY,
                    "reference_code": self.random.choice(HINT_REFERENCES[bucket]).format(n=self.next_number()),
                    "description": self.random.choice(HINT_DESCRIPTIONS[bucket]),
                }
                rows.append(row)
                grouped[(bucket, channel)].append(row)
                answers.append({
                    "deduction_id": deduction_id, "seed_category": "classifiable",
                    "true_bucket": bucket, "matched_accrual_id": None,
                    "supporting_accrual_id": None,
                    "notes": "no exact transaction match; bucket is inferable and a programme balance is available",
                })

        pools, pool_ids = [], {}
        for (bucket, channel), deductions in sorted(grouped.items()):
            total = round(sum(abs(row["amount"]) for row in deductions) * 1.10, 2)
            accrual_id = f"ACR-2026-{self.next_number():05d}"
            pool_ids[(bucket, channel)] = accrual_id
            pools.append({
                "accrual_id": accrual_id, "accrual_date": "2026-06-15",
                "accrual_period": "2026-06", "vendor_name": channel,
                "bucket": bucket, "amount": total, "currency": CURRENCY,
                "reference_code": f"SAP-POOL-{self.next_number():04d}",
                "description": f"{bucket} - programme evidence balance",
                "evidence_scope": "programme_pool",
            })
        row_by_id = {row["deduction_id"]: row for row in rows}
        for answer in answers:
            row = row_by_id[answer["deduction_id"]]
            channel = next(channel for channel, variants in CHANNELS.items()
                           if vendor_score(row["vendor_name"], channel) >= 60)
            answer["supporting_accrual_id"] = pool_ids[(answer["true_bucket"], channel)]
        return rows, answers, pools

    def unresolvable_rows(self):
        rows, answers = [], []
        for _ in range(25):
            amount = round(self.random.choice([40, 60, 75.50, 100, 150, 200, 325]) + self.random.uniform(-5, 5), 2)
            deduction_id = f"DED-2026-{self.next_number():05d}"
            rows.append({
                "deduction_id": deduction_id, "transaction_date": self.random_date().isoformat(),
                "vendor_name": self.random.choice(UNRESOLVABLE_VENDORS),
                "amount": -abs(amount), "currency": CURRENCY,
                "reference_code": self.random.choice(GENERIC_REFERENCES).format(n=self.next_number()),
                "description": self.random.choice(UNRESOLVABLE_DESCRIPTIONS),
            })
            answers.append({
                "deduction_id": deduction_id, "seed_category": "unresolvable",
                "true_bucket": None, "matched_accrual_id": None, "supporting_accrual_id": None,
                "notes": "no bucket signal and no exact-amount near-date ledger candidate",
            })
        return rows, answers

    def build(self):
        transaction_accruals, _ = self.transaction_accruals()
        match_rows, match_answers = self.matchable_rows(transaction_accruals)
        class_rows, class_answers, pools = self.classifiable_rows()
        unres_rows, unres_answers = self.unresolvable_rows()
        settlements = match_rows + class_rows + unres_rows
        answers = match_answers + class_answers + unres_answers
        combined = list(zip(settlements, answers))
        self.random.shuffle(combined)
        settlements, answers = map(list, zip(*combined))
        accruals = transaction_accruals + pools
        self.random.shuffle(accruals)
        return settlements, accruals, answers


def write_csv(path: Path, rows, fieldnames) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_deterministic_gzip_json(path: Path, data) -> None:
    encoded = (json.dumps(data, indent=2) + "\n").encode("utf-8")
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            zipped.write(encoded)


def generate(out_dir: Path = DEFAULT_OUT_DIR, seed: int = SEED) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    settlements, accruals, answers = Generator(seed).build()
    settlement_path = out_dir / "settlement_deductions.csv"
    accrual_path = out_dir / "invoice_accruals.csv"
    answer_path = out_dir / "answer_key.json.gz"
    write_csv(settlement_path, settlements, [
        "deduction_id", "transaction_date", "vendor_name", "amount", "currency",
        "reference_code", "description",
    ])
    write_csv(accrual_path, accruals, [
        "accrual_id", "accrual_date", "accrual_period", "vendor_name", "bucket",
        "amount", "currency", "reference_code", "description", "evidence_scope",
    ])
    write_deterministic_gzip_json(answer_path, {
        "dataset_version": "2.0.0", "ruleset_version": RULESET_VERSION,
        "generated_with_seed": seed,
        "counts": {"total_settlement_lines": len(settlements), "auto_matched": 150,
                   "classifiable": 75, "unresolvable": 25},
        "entries": answers,
    })
    return {"settlements": settlement_path, "accruals": accrual_path, "answer_key": answer_path}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    paths = generate(args.out_dir, args.seed)
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
