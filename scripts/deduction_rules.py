"""Canonical V2 matching and evidence rules used by fixtures and tests.

The n8n workflow mirrors these rules in JavaScript. ``RULESET_VERSION`` is
written into both implementations so parity can be checked automatically.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

RULESET_VERSION = "2.0.0"

VENDOR_ALIAS_PATTERNS = {
    "amazon": ("amazon", "amzn", "mktp"),
    "walmart": ("walmart",),
    "target": ("target",),
    "costco": ("costco",),
    "shopify direct": ("shopify",),
}


def normalise_vendor(value: str | None) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    return re.sub(r"\s+", " ", text)


def canonical_vendor(value: str | None) -> str:
    normalised = normalise_vendor(value)
    tokens = set(normalised.split())
    for canonical, patterns in VENDOR_ALIAS_PATTERNS.items():
        if any(pattern in tokens for pattern in patterns):
            return canonical
    return normalised


def vendor_score(first: str | None, second: str | None) -> int:
    a, b = canonical_vendor(first), canonical_vendor(second)
    if not a or not b:
        return 0
    if a == b:
        return 100
    if a in b or b in a:
        return 90
    tokens_a, tokens_b = a.split(), b.split()
    overlap = {token for token in tokens_a if token in set(tokens_b) and len(token) >= 3}
    if not overlap:
        return 0
    return 70 if len(overlap) >= min(len(tokens_a), len(tokens_b)) else 60


def days_between(first: str, second: str) -> int:
    return abs((date.fromisoformat(first) - date.fromisoformat(second)).days)


def to_cents(value: float | str) -> int:
    return round(abs(float(value)) * 100)


def allocate_evidence(
    classifications: list[dict[str, Any]],
    accruals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Allocate programme-pool balances once across a complete classified run.

    This testable Python implementation is mirrored by the V2 n8n verification
    node. It deliberately processes the full run rather than resetting balances
    for each LLM batch.
    """
    accrual_ids = [str(row.get("accrual_id") or "").strip() for row in accruals]
    if any(not identifier for identifier in accrual_ids) or len(set(accrual_ids)) != len(accrual_ids):
        raise ValueError("Every accrual_id must be present and unique")
    pools = {
        row["accrual_id"]: {
            **row,
            "available_cents": to_cents(row["amount"]),
        }
        for row in accruals
        if row.get("evidence_scope") == "programme_pool"
    }
    all_accruals = list(accruals)
    ordered = sorted(classifications, key=lambda row: (-to_cents(row.get("amount", 0)), row["deduction_id"]))
    routed: dict[str, dict[str, Any]] = {}

    for row in ordered:
        amount_cents = to_cents(row.get("amount", 0))
        settlement_date = row.get("_normalised_date") or row.get("transaction_date")
        settlement_vendor = row.get("_normalised_vendor") or row.get("vendor_name")
        bucket = row.get("llm_bucket")

        if bucket == "Unresolvable":
            exact_candidate = next(
                (
                    accrual for accrual in all_accruals
                    if to_cents(accrual["amount"]) == amount_cents
                    and days_between(settlement_date, accrual["accrual_date"]) <= 1
                    and vendor_score(settlement_vendor, accrual.get("vendor_name")) >= 60
                ),
                None,
            )
            if exact_candidate:
                routed[row["deduction_id"]] = {
                    **row,
                    "_route": "needs_review",
                    "_evidence_agrees": False,
                    "_evidence_note": (
                        "AI proposed Unresolvable, but an exact-amount near-date accrual "
                        f"candidate exists ({exact_candidate['accrual_id']}); human review required."
                    ),
                }
            else:
                routed[row["deduction_id"]] = {
                    **row,
                    "_route": "unresolvable",
                    "_evidence_agrees": True,
                    "_evidence_note": "No exact-amount near-date candidate exists in the supplied ledger.",
                }
            continue

        candidates = []
        for pool in pools.values():
            if pool.get("bucket") != bucket or pool["available_cents"] < amount_cents:
                continue
            score = vendor_score(settlement_vendor, pool.get("vendor_name"))
            if score < 60:
                continue
            delta = days_between(settlement_date, pool["accrual_date"])
            if delta > 45:
                continue
            candidates.append((-score, delta, pool["accrual_id"], pool))

        if not candidates:
            routed[row["deduction_id"]] = {
                **row,
                "_route": "needs_review",
                "_evidence_agrees": False,
                "_evidence_note": "No same-vendor programme balance can support the proposed bucket and amount.",
            }
            continue

        pool = sorted(candidates)[0][3]
        before = pool["available_cents"]
        pool["available_cents"] -= amount_cents
        routed[row["deduction_id"]] = {
            **row,
            "_route": "classified_verified",
            "_evidence_agrees": True,
            "_evidence_accrual_id": pool["accrual_id"],
            "_allocated_amount": amount_cents / 100,
            "_evidence_balance_before": before / 100,
            "_evidence_balance_after": pool["available_cents"] / 100,
            "_evidence_note": (
                f"Allocated £{amount_cents / 100:,.2f} against programme balance "
                f"{pool['accrual_id']}; £{pool['available_cents'] / 100:,.2f} remains."
            ),
        }

    return [routed[row["deduction_id"]] for row in classifications]
