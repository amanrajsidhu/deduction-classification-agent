"""
Synthetic dataset generator for the Deduction & Exception Classification demo.

Produces two working CSVs (settlement/deduction lines, invoice/accrual lines)
and a separately-stored, gzip-sealed answer key. Deterministic (fixed seed)
so re-runs are reproducible.

Seeded split across the 250 settlement lines, per build brief Section 5:
  - 60% (150) deterministically matchable  -> resolved in Stage 4, never reach the LLM
  - 30% (75)  classifiable from line evidence -> LLM + evidence check should get these right
  - 10% (25)  genuinely unresolvable -> correct answer is "cannot be determined from data alone"
"""

import csv
import gzip
import json
import os
import random
from datetime import date, timedelta
from difflib import SequenceMatcher

random.seed(42)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
SETTLEMENT_PATH = os.path.join(OUT_DIR, "settlement_deductions.csv")
ACCRUAL_PATH = os.path.join(OUT_DIR, "invoice_accruals.csv")
ANSWER_KEY_PATH = os.path.join(OUT_DIR, "answer_key.json.gz")

CURRENCY = "GBP"
PERIOD_START = date(2026, 6, 1)
PERIOD_END = date(2026, 6, 30)

BUCKETS = [
    "Promotional Accrual",
    "Shortage Claim",
    "Price Dispute",
    "Damaged Goods",
    "Chargeback/Other",
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

GARBLED_VENDOR_VARIANTS = [
    "MKTPL-SETTLEMENT-EU",
    "PARTNER-99231-REMIT",
    "3P-SELLER-PAYOUTS",
    "EXTERNAL SETTLEMENT CO",
    "DEDUCTION PROCESSOR LTD",
]

VAGUE_UNRESOLVABLE_VENDORS = [
    "Marketplace Services Ltd",
    "3rd Party Payment Processor",
    "Unknown Remitter",
    "Payments Clearing House",
]

GENERIC_REFERENCE_TEMPLATES = ["ADJ-{n}", "DED-{n}", "REF-{n}", "SETTLEMENT-{n}", "NOTE-{n}"]

STRONG_HINT_REFERENCE_TEMPLATES = {
    "Promotional Accrual": ["PROMO-{n}", "MKTG-REBATE-{n}", "TRADE-PROMO-{n}"],
    "Shortage Claim": ["SHORT-{n}", "QTY-SHORT-{n}", "MISSING-UNITS-{n}"],
    "Price Dispute": ["PRC-DISP-{n}", "PRICE-ADJ-{n}", "PPD-{n}"],
    "Damaged Goods": ["DMG-CLAIM-{n}", "DAMAGED-RMA-{n}", "WHSE-DMG-{n}"],
    "Chargeback/Other": ["CHB-{n}", "MISC-ADJ-{n}", "OTHER-DEDUCT-{n}"],
}

GENERIC_DESCRIPTIONS = [
    "Reimbursement adjustment - see portal",
    "Deduction per remittance advice",
    "Account adjustment - refer to statement",
    "Miscellaneous deduction - see note",
    "Adjustment applied at settlement",
]

BUCKET_HINT_DESCRIPTIONS = {
    "Promotional Accrual": ["Aggregated promo rebate - multiple campaigns", "Trade promotion funding adjustment", "Marketing rebate accrual drawdown"],
    "Shortage Claim": ["Aggregated shortage adjustment - multiple SKUs", "Inventory receipt shortfall claim", "Units short on receipt - claim filed"],
    "Price Dispute": ["Retroactive price adjustment - multiple POs", "Cost price discrepancy claim", "Price protection dispute adjustment"],
    "Damaged Goods": ["Warehouse damage claim - multiple units", "Inbound damage adjustment", "Damaged inventory write-down claim"],
    "Chargeback/Other": ["Aggregated chargeback - see case file", "Miscellaneous marketplace deduction", "Other adjustment - multiple references"],
}

VAGUE_UNRESOLVABLE_DESCRIPTIONS = [
    "Account adjustment - see remittance advice",
    "Miscellaneous deduction - refer to portal",
    "Balance adjustment - no further detail",
    "General ledger adjustment",
]


def fuzzy_ratio(a: str, b: str) -> float:
    """Best-window partial ratio (similar in spirit to a partial/token fuzzy matcher) -
    a straight whole-string SequenceMatcher ratio unfairly penalises 'Amazon' vs
    'Amazon Services Europe' purely for length, which isn't how vendor fuzzy-matching
    behaves in practice."""
    a, b = a.lower(), b.lower()
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if not shorter:
        return 0.0
    best = 0.0
    for i in range(len(longer) - len(shorter) + 1):
        window = longer[i:i + len(shorter)]
        best = max(best, SequenceMatcher(None, shorter, window).ratio())
    return best * 100


def random_date_in_period(start=PERIOD_START, end=PERIOD_END) -> date:
    span = (end - start).days
    return start + timedelta(days=random.randint(0, span))


def random_amount(bucket: str) -> float:
    lo, hi = AMOUNT_RANGES[bucket]
    return round(random.uniform(lo, hi), 2)


def pick_clean_vendor_variant(channel: str) -> str:
    variant = random.choice(CHANNELS[channel])
    assert fuzzy_ratio(variant, channel) >= 60, f"variant '{variant}' too dissimilar from '{channel}'"
    return variant


def next_counter():
    next_counter.n += 1
    return next_counter.n


next_counter.n = 0


def build_accrual_rows():
    rows = []
    by_bucket = {b: [] for b in BUCKETS}
    for bucket in BUCKETS:
        for _ in range(30):
            channel = random.choice(list(CHANNELS.keys()))
            accrual_date = random_date_in_period()
            amount = random_amount(bucket)
            accrual_id = f"ACR-2026-{next_counter():05d}"
            row = {
                "accrual_id": accrual_id,
                "accrual_date": accrual_date.isoformat(),
                "accrual_period": "2026-06",
                "vendor_name": channel,
                "bucket": bucket,
                "amount": amount,
                "currency": CURRENCY,
                "reference_code": f"SAP-BKT-{next_counter():04d}",
                "description": f"{bucket} - internal accrual entry",
            }
            rows.append(row)
            by_bucket[bucket].append(row)
    return rows, by_bucket


def build_matchable_settlement_rows(accrual_rows):
    settlement_rows = []
    answer_entries = []
    for accrual in accrual_rows:
        channel = accrual["vendor_name"]
        bucket = accrual["bucket"]
        settlement_date = date.fromisoformat(accrual["accrual_date"]) + timedelta(days=random.choice([-1, 0, 1]))
        amount_noise = random.choice([0.0, 0.0, 0.0, 0.01, -0.01])
        amount = round(accrual["amount"] + amount_noise, 2)
        vendor_name = pick_clean_vendor_variant(channel)
        deduction_id = f"DED-2026-{next_counter():05d}"
        ref_template = random.choice(GENERIC_REFERENCE_TEMPLATES)
        settlement_rows.append({
            "deduction_id": deduction_id,
            "transaction_date": settlement_date.isoformat(),
            "vendor_name": vendor_name,
            "amount": -abs(amount),
            "currency": CURRENCY,
            "reference_code": ref_template.format(n=next_counter()),
            "description": random.choice(GENERIC_DESCRIPTIONS),
        })
        answer_entries.append({
            "deduction_id": deduction_id,
            "seed_category": "auto_matched",
            "true_bucket": bucket,
            "matched_accrual_id": accrual["accrual_id"],
            "notes": "exact amount/date/vendor match to dedicated accrual line",
        })
    return settlement_rows, answer_entries


def build_classifiable_settlement_rows(accrual_by_bucket):
    settlement_rows = []
    answer_entries = []
    failure_reasons = ["amount_off", "date_off", "vendor_garbled"]
    for bucket in BUCKETS:
        bucket_accruals = accrual_by_bucket[bucket]
        for _ in range(15):
            failure_reason = random.choice(failure_reasons)
            anchor = random.choice(bucket_accruals)
            channel = anchor["vendor_name"]

            if failure_reason == "amount_off":
                amount = round(anchor["amount"] * random.uniform(1.3, 1.9), 2)
                settlement_date = date.fromisoformat(anchor["accrual_date"]) + timedelta(days=random.choice([-1, 0, 1]))
                vendor_name = pick_clean_vendor_variant(channel)
            elif failure_reason == "date_off":
                amount = round(anchor["amount"] + random.choice([0.0, 0.01, -0.01]), 2)
                settlement_date = date.fromisoformat(anchor["accrual_date"]) + timedelta(days=random.randint(4, 12) * random.choice([-1, 1]))
                vendor_name = pick_clean_vendor_variant(channel)
            else:
                amount = random_amount(bucket)
                settlement_date = random_date_in_period()
                vendor_name = random.choice(GARBLED_VENDOR_VARIANTS)
                assert fuzzy_ratio(vendor_name, channel) < 60

            deduction_id = f"DED-2026-{next_counter():05d}"
            ref_template = random.choice(STRONG_HINT_REFERENCE_TEMPLATES[bucket])
            settlement_rows.append({
                "deduction_id": deduction_id,
                "transaction_date": settlement_date.isoformat(),
                "vendor_name": vendor_name,
                "amount": -abs(amount),
                "currency": CURRENCY,
                "reference_code": ref_template.format(n=next_counter()),
                "description": random.choice(BUCKET_HINT_DESCRIPTIONS[bucket]),
            })
            answer_entries.append({
                "deduction_id": deduction_id,
                "seed_category": "classifiable",
                "true_bucket": bucket,
                "matched_accrual_id": None,
                "notes": f"fails deterministic match on {failure_reason}; bucket inferable from reference/description",
            })
    return settlement_rows, answer_entries


def build_unresolvable_settlement_rows():
    settlement_rows = []
    answer_entries = []
    for _ in range(25):
        settlement_date = random_date_in_period()
        amount = round(random.choice([100.00, 150.00, 200.00, 75.50, 325.00, 40.00, 60.00]) + random.uniform(-5, 5), 2)
        vendor_name = random.choice(VAGUE_UNRESOLVABLE_VENDORS)
        deduction_id = f"DED-2026-{next_counter():05d}"
        ref_template = random.choice(GENERIC_REFERENCE_TEMPLATES)
        settlement_rows.append({
            "deduction_id": deduction_id,
            "transaction_date": settlement_date.isoformat(),
            "vendor_name": vendor_name,
            "amount": -abs(amount),
            "currency": CURRENCY,
            "reference_code": ref_template.format(n=next_counter()),
            "description": random.choice(VAGUE_UNRESOLVABLE_DESCRIPTIONS),
        })
        answer_entries.append({
            "deduction_id": deduction_id,
            "seed_category": "unresolvable",
            "true_bucket": None,
            "matched_accrual_id": None,
            "notes": "no plausible bucket/accrual signal; requires external info to resolve",
        })
    return settlement_rows, answer_entries


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    accrual_rows, accrual_by_bucket = build_accrual_rows()
    matched_rows, matched_answers = build_matchable_settlement_rows(accrual_rows)
    classifiable_rows, classifiable_answers = build_classifiable_settlement_rows(accrual_by_bucket)
    unresolvable_rows, unresolvable_answers = build_unresolvable_settlement_rows()

    settlement_rows = matched_rows + classifiable_rows + unresolvable_rows
    answer_entries = matched_answers + classifiable_answers + unresolvable_answers

    combined = list(zip(settlement_rows, answer_entries))
    random.shuffle(combined)
    settlement_rows, answer_entries = zip(*combined)
    settlement_rows, answer_entries = list(settlement_rows), list(answer_entries)

    random.shuffle(accrual_rows)

    write_csv(
        SETTLEMENT_PATH,
        settlement_rows,
        ["deduction_id", "transaction_date", "vendor_name", "amount", "currency", "reference_code", "description"],
    )
    write_csv(
        ACCRUAL_PATH,
        accrual_rows,
        ["accrual_id", "accrual_date", "accrual_period", "vendor_name", "bucket", "amount", "currency", "reference_code", "description"],
    )

    answer_key = {
        "generated_with_seed": 42,
        "counts": {
            "total_settlement_lines": len(settlement_rows),
            "auto_matched": len(matched_answers),
            "classifiable": len(classifiable_answers),
            "unresolvable": len(unresolvable_answers),
        },
        "entries": answer_entries,
    }
    with gzip.open(ANSWER_KEY_PATH, "wt", encoding="utf-8") as f:
        json.dump(answer_key, f, indent=2)

    print(f"Wrote {len(settlement_rows)} settlement lines -> {SETTLEMENT_PATH}")
    print(f"Wrote {len(accrual_rows)} accrual lines -> {ACCRUAL_PATH}")
    print(f"Wrote sealed answer key -> {ANSWER_KEY_PATH}")
    print("Answer key is gzip-compressed JSON - do not open before the blind manual baseline pass (Section 9).")


if __name__ == "__main__":
    main()
