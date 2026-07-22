"""
Six-tab XLSX generator for the Deduction & Exception Classification demo.

Reads the five JSON exports written by the n8n workflow (docker-cp'd out of the
container into outputs/_n8n_export/) plus the sealed answer key, scores the
workflow's output against the seed key, and writes the final six-tab XLSX.

This is a variant, not a reuse of the old five-tab reconciliation template
(build_brief.md Section 8) - the schema here is classification-shaped, not
bank-rec-shaped.

Usage:
    python scripts/generate_xlsx_output.py
"""

import gzip
import json
import os
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
N8N_EXPORT_DIR = OUT_DIR
ANSWER_KEY_PATH = os.path.join(OUT_DIR, "answer_key.json.gz")
XLSX_OUTPUT_PATH = os.path.join(OUT_DIR, "deduction_classification_output.xlsx")

HEADER_FILL = PatternFill(start_color="1F2933", end_color="1F2933", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)
TITLE_FONT = Font(bold=True, size=14)
METRIC_LABEL_FONT = Font(bold=True)
STATUS_FILLS = {
    "Excellent": PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
    "Good": PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid"),
    "Needs Review": PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid"),
}


def load_json_list(path):
    if not os.path.exists(path):
        print(f"WARNING: expected output file not found: {path} (treating as 0 records)")
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    return data


def load_answer_key(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    entries = {e["deduction_id"]: e for e in data["entries"]}
    return data["counts"], entries


def status_label(rate):
    if rate >= 0.95:
        return "Excellent"
    if rate >= 0.85:
        return "Good"
    return "Needs Review"


def dedupe_token_totals(records):
    seen_calls = {}
    for r in records:
        call_id = r.get("_llm_call_id")
        if not call_id or call_id in seen_calls:
            continue
        seen_calls[call_id] = {
            "input_tokens": r.get("input_tokens") or 0,
            "output_tokens": r.get("output_tokens") or 0,
            "cache_creation_input_tokens": r.get("cache_creation_input_tokens") or 0,
            "cache_read_input_tokens": r.get("cache_read_input_tokens") or 0,
        }
    totals = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "calls": len(seen_calls)}
    for v in seen_calls.values():
        totals["input_tokens"] += v["input_tokens"]
        totals["output_tokens"] += v["output_tokens"]
        totals["cache_creation_input_tokens"] += v["cache_creation_input_tokens"]
        totals["cache_read_input_tokens"] += v["cache_read_input_tokens"]
    return totals


def compute_metrics(auto_matched, classified_verified, needs_review, unresolvable, data_quality, answer_entries):
    total_lines = len(auto_matched) + len(classified_verified) + len(needs_review) + len(unresolvable) + len(data_quality)

    match_rate = len(auto_matched) / total_lines if total_lines else 0.0

    classified_correct = sum(
        1 for r in classified_verified
        if answer_entries.get(r.get("deduction_id"), {}).get("true_bucket") == r.get("llm_bucket")
    )
    classification_accuracy = classified_correct / len(classified_verified) if classified_verified else None

    seeded_unresolvable_ids = [did for did, e in answer_entries.items() if e["seed_category"] == "unresolvable"]
    workflow_unresolvable_ids = {r.get("deduction_id") for r in unresolvable}
    correctly_flagged = sum(1 for did in seeded_unresolvable_ids if did in workflow_unresolvable_ids)
    unresolvable_flagging_accuracy = (
        correctly_flagged / len(seeded_unresolvable_ids) if seeded_unresolvable_ids else None
    )

    seeded_auto_matched_ids = [did for did, e in answer_entries.items() if e["seed_category"] == "auto_matched"]
    workflow_auto_matched_ids = {r.get("deduction_id") for r in auto_matched}
    auto_match_recall_count = sum(1 for did in seeded_auto_matched_ids if did in workflow_auto_matched_ids)
    auto_match_recall = (
        auto_match_recall_count / len(seeded_auto_matched_ids) if seeded_auto_matched_ids else None
    )

    pair_correct = sum(
        1 for r in auto_matched
        if answer_entries.get(r.get("deduction_id"), {}).get("matched_accrual_id") == r.get("matched_accrual_id")
    )
    pair_correctness = pair_correct / len(auto_matched) if auto_matched else None

    token_totals = dedupe_token_totals(classified_verified + needs_review + unresolvable)

    return {
        "total_lines": total_lines,
        "auto_matched_count": len(auto_matched),
        "classified_verified_count": len(classified_verified),
        "needs_review_count": len(needs_review),
        "unresolvable_count": len(unresolvable),
        "data_quality_count": len(data_quality),
        "match_rate": match_rate,
        "classification_accuracy": classification_accuracy,
        "classified_correct": classified_correct,
        "unresolvable_flagging_accuracy": unresolvable_flagging_accuracy,
        "seeded_unresolvable_total": len(seeded_unresolvable_ids),
        "unresolvable_correctly_flagged": correctly_flagged,
        "auto_match_recall": auto_match_recall,
        "auto_match_recall_count": auto_match_recall_count,
        "seeded_auto_matched_total": len(seeded_auto_matched_ids),
        "pair_correctness": pair_correctness,
        "pair_correct_count": pair_correct,
        "token_totals": token_totals,
    }


def autosize_columns(ws, min_width=10, max_width=60):
    widths = {}
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is None:
                continue
            col = cell.column_letter
            length = len(str(cell.value))
            widths[col] = max(widths.get(col, 0), length)
    for col, width in widths.items():
        ws.column_dimensions[col].width = min(max(width + 2, min_width), max_width)


def write_header(ws, headers, row=1):
    for idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=idx, value=h)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center")
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def write_line_items_tab(ws, records, columns):
    write_header(ws, [c[1] for c in columns])
    for row_idx, r in enumerate(records, start=2):
        for col_idx, (key, _label) in enumerate(columns, start=1):
            ws.cell(row=row_idx, column=col_idx, value=r.get(key))
    autosize_columns(ws)


AUTO_MATCHED_COLUMNS = [
    ("deduction_id", "Deduction ID"),
    ("transaction_date", "Transaction Date"),
    ("vendor_name", "Vendor Name"),
    ("amount", "Amount"),
    ("currency", "Currency"),
    ("reference_code", "Reference Code"),
    ("description", "Description"),
    ("matched_accrual_id", "Matched Accrual ID"),
    ("matched_bucket", "Matched Bucket"),
    ("vendor_score", "Vendor Score"),
    ("date_delta_days", "Date Delta (days)"),
    ("match_reason", "Match Reason"),
]

CLASSIFIED_VERIFIED_COLUMNS = [
    ("deduction_id", "Deduction ID"),
    ("transaction_date", "Transaction Date"),
    ("vendor_name", "Vendor Name"),
    ("amount", "Amount"),
    ("currency", "Currency"),
    ("reference_code", "Reference Code"),
    ("description", "Description"),
    ("llm_bucket", "Classified Bucket"),
    ("llm_confidence", "Confidence"),
    ("llm_reasoning", "Reasoning"),
    ("_evidence_accrual_id", "Evidence Accrual ID"),
    ("_evidence_note", "Evidence Note"),
]

NEEDS_REVIEW_COLUMNS = [
    ("deduction_id", "Deduction ID"),
    ("transaction_date", "Transaction Date"),
    ("vendor_name", "Vendor Name"),
    ("amount", "Amount"),
    ("currency", "Currency"),
    ("reference_code", "Reference Code"),
    ("description", "Description"),
    ("llm_bucket", "LLM-Claimed Bucket"),
    ("llm_confidence", "Confidence"),
    ("llm_reasoning", "LLM Reasoning"),
    ("_classification_error", "Classification Error"),
    ("_evidence_note", "Evidence Note / Reason for Review"),
]

UNRESOLVABLE_COLUMNS = [
    ("deduction_id", "Deduction ID"),
    ("transaction_date", "Transaction Date"),
    ("vendor_name", "Vendor Name"),
    ("amount", "Amount"),
    ("currency", "Currency"),
    ("reference_code", "Reference Code"),
    ("description", "Description"),
    ("llm_confidence", "Confidence"),
    ("llm_reasoning", "LLM Reasoning"),
    ("_evidence_note", "Evidence Note"),
]

DATA_QUALITY_COLUMNS = [
    ("deduction_id", "Deduction ID"),
    ("transaction_date", "Raw Transaction Date"),
    ("vendor_name", "Vendor Name"),
    ("amount", "Amount"),
    ("currency", "Currency"),
    ("reference_code", "Reference Code"),
    ("description", "Description"),
    ("_date_parse_method", "Date Parse Result"),
    ("error", "Error Type"),
]


def build_summary_tab(ws, metrics, seed_counts):
    ws.cell(row=1, column=1, value="Deduction & Exception Classification - Run Summary").font = TITLE_FONT
    ws.cell(row=2, column=1, value=f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    write_header(ws, ["Metric", "Value", "Notes"], row=4)

    rows = [
        ("Total Settlement Lines", metrics["total_lines"], ""),
        ("Auto-Matched", f'{metrics["auto_matched_count"]} ({metrics["auto_matched_count"] / metrics["total_lines"]:.1%})', "Resolved deterministically, never reached the LLM"),
        ("Classified & Verified", f'{metrics["classified_verified_count"]} ({metrics["classified_verified_count"] / metrics["total_lines"]:.1%})', "LLM classification + evidence check agreed"),
        ("Needs Review", f'{metrics["needs_review_count"]} ({metrics["needs_review_count"] / metrics["total_lines"]:.1%})', "LLM/evidence disagreed, or malformed LLM output"),
        ("Unresolvable", f'{metrics["unresolvable_count"]} ({metrics["unresolvable_count"] / metrics["total_lines"]:.1%})', "No plausible bucket found in the ledger"),
        ("Data Quality Issues", f'{metrics["data_quality_count"]} ({metrics["data_quality_count"] / metrics["total_lines"]:.1%})', "Failed basic parsing (e.g. ambiguous dates)"),
        ("Match Rate", f'{metrics["match_rate"]:.1%}', "Auto-Matched / Total Settlement Lines"),
        (
            "Auto-Match Recall (vs seeded)",
            f'{metrics["auto_match_recall"]:.1%}' if metrics["auto_match_recall"] is not None else "n/a",
            f'{metrics["auto_match_recall_count"]} of {metrics["seeded_auto_matched_total"]} seeded auto-matchable lines were found and auto-matched',
        ),
        (
            "Auto-Match Pair Correctness",
            f'{metrics["pair_correctness"]:.1%}' if metrics["pair_correctness"] is not None else "n/a",
            f'{metrics["pair_correct_count"]} of {metrics["auto_matched_count"]} auto-matched lines were paired with the correct accrual (zero false matches if 100%)',
        ),
        (
            "Classification Accuracy (vs seed key)",
            f'{metrics["classification_accuracy"]:.1%}' if metrics["classification_accuracy"] is not None else "n/a",
            f'{metrics["classified_correct"]} of {metrics["classified_verified_count"]} Classified & Verified lines matched the seeded true bucket',
        ),
        (
            "Unresolvable-Flagging Accuracy",
            f'{metrics["unresolvable_flagging_accuracy"]:.1%}' if metrics["unresolvable_flagging_accuracy"] is not None else "n/a",
            f'{metrics["unresolvable_correctly_flagged"]} of {metrics["seeded_unresolvable_total"]} genuinely-unresolvable seeded lines correctly flagged',
        ),
        ("Claude API Calls (this run)", metrics["token_totals"]["calls"], "Deduplicated by response ID"),
        ("Total Input Tokens", metrics["token_totals"]["input_tokens"], "Real usage from the Anthropic API, not estimated"),
        ("Total Output Tokens", metrics["token_totals"]["output_tokens"], "Real usage from the Anthropic API, not estimated"),
        ("Cache Creation Input Tokens", metrics["token_totals"]["cache_creation_input_tokens"], "0 expected - no prompt caching in V1"),
        ("Cache Read Input Tokens", metrics["token_totals"]["cache_read_input_tokens"], "0 expected - no prompt caching in V1"),
    ]

    r = 5
    for label, value, note in rows:
        ws.cell(row=r, column=1, value=label).font = METRIC_LABEL_FONT
        ws.cell(row=r, column=2, value=value)
        ws.cell(row=r, column=3, value=note)
        r += 1

    status = status_label(metrics["classification_accuracy"] if metrics["classification_accuracy"] is not None else 1.0)
    status_row = r + 1
    ws.cell(row=status_row, column=1, value="Overall Status").font = METRIC_LABEL_FONT
    status_cell = ws.cell(row=status_row, column=2, value=status)
    status_cell.fill = STATUS_FILLS[status]
    ws.cell(row=status_row, column=3, value="Based on Classification Accuracy - Excellent >=95%, Good >=85%, else Needs Review")

    seed_row = status_row + 2
    ws.cell(row=seed_row, column=1, value="Seed dataset split (for reference)").font = METRIC_LABEL_FONT
    ws.cell(row=seed_row + 1, column=1, value=f'Auto-matched (seeded): {seed_counts["auto_matched"]}')
    ws.cell(row=seed_row + 2, column=1, value=f'Classifiable (seeded): {seed_counts["classifiable"]}')
    ws.cell(row=seed_row + 3, column=1, value=f'Unresolvable (seeded): {seed_counts["unresolvable"]}')

    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 70


def main():
    auto_matched = load_json_list(os.path.join(N8N_EXPORT_DIR, "auto_matched.json"))
    classified_verified = load_json_list(os.path.join(N8N_EXPORT_DIR, "classified_verified.json"))
    needs_review = load_json_list(os.path.join(N8N_EXPORT_DIR, "needs_review.json"))
    unresolvable = load_json_list(os.path.join(N8N_EXPORT_DIR, "unresolvable.json"))
    data_quality = load_json_list(os.path.join(N8N_EXPORT_DIR, "data_quality_issues.json"))

    seed_counts, answer_entries = load_answer_key(ANSWER_KEY_PATH)

    metrics = compute_metrics(auto_matched, classified_verified, needs_review, unresolvable, data_quality, answer_entries)

    wb = Workbook()
    summary_ws = wb.active
    summary_ws.title = "Summary"
    build_summary_tab(summary_ws, metrics, seed_counts)

    write_line_items_tab(wb.create_sheet("Auto_Matched"), auto_matched, AUTO_MATCHED_COLUMNS)
    write_line_items_tab(wb.create_sheet("Classified_Verified"), classified_verified, CLASSIFIED_VERIFIED_COLUMNS)
    write_line_items_tab(wb.create_sheet("Needs_Review"), needs_review, NEEDS_REVIEW_COLUMNS)
    write_line_items_tab(wb.create_sheet("Unresolvable"), unresolvable, UNRESOLVABLE_COLUMNS)
    write_line_items_tab(wb.create_sheet("Data_Quality_Issues"), data_quality, DATA_QUALITY_COLUMNS)

    os.makedirs(OUT_DIR, exist_ok=True)
    wb.save(XLSX_OUTPUT_PATH)

    print(f"Wrote {XLSX_OUTPUT_PATH}")
    print(f"Total lines: {metrics['total_lines']}")
    print(f"Match rate: {metrics['match_rate']:.1%}")
    if metrics["classification_accuracy"] is not None:
        print(f"Classification accuracy: {metrics['classification_accuracy']:.1%}")
    if metrics["unresolvable_flagging_accuracy"] is not None:
        print(f"Unresolvable-flagging accuracy: {metrics['unresolvable_flagging_accuracy']:.1%}")


if __name__ == "__main__":
    main()
