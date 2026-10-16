# Deduction Resolution Workbench — agent instructions

Public-safe instructions shared by Codex and Claude Code. This repository is public: keep this file free of
machine-local paths, workflow IDs, credential names, execution IDs and anything client-related.
Machine-local operator context lives in the gitignored `CLAUDE.md` in this folder; read it if it exists.

## Purpose

Repair and productise the existing deduction-classification demo as a public,
synthetic proof asset and service wedge. It must reduce manual deduction sorting
without presenting AI as an accounting authority.

## Product controls

1. Validate dates, amounts and counterparty names.
2. Canonicalise configured counterparty aliases.
3. Match exact-value, near-date, same-counterparty accruals one-to-one.
4. Treat configured reference aliases as authoritative before AI proposals.
5. Allocate same-counterparty programme balances once across the full run.
6. Fail closed to review when evidence conflicts, is missing or is exhausted.
7. Always write all five output files, including empty arrays.
8. Never post journals, write-offs, disputes or approvals.
9. Never persist provider response IDs; public rows use local batch references.

## Source of truth

- Product promise and authority: `docs/00_PRODUCT_CONTRACT.md`
- Evaluation rules: `docs/01_EVALUATION.md`
- Security boundary: `docs/SECURITY_AND_DATA_BOUNDARY.md`
- Risks: `docs/03_RISK_REGISTER.md`
- Build decisions and verified result: `docs/BUILD_NOTES.md`
- Workflow generator: `scripts/upgrade_workflow_v2.py`
- Evaluator/workbook generator: `scripts/generate_xlsx_output.py`
- Live export: `workflows/DEDUCTION_RESOLUTION_WORKBENCH_V2.json`

## Verified result

The verified baseline, its counts and the commit it is tied to are recorded in `docs/BUILD_NOTES.md`.
Results are synthetic and must not be described as production accuracy.

## Safety

- Never print or commit `.env` contents, tokens, signing secrets, encryption keys or credential values.
- Do not publish, push, activate or deploy anything without explicit user instruction for that action.

## Required checks before calling a result complete

```text
python -m unittest discover -s tests -v
python scripts/finalize_run.py --outputs-dir outputs/v2 --settlement-csv fixtures/v2/settlement_deductions.csv
python scripts/generate_xlsx_output.py --outputs-dir outputs/v2 --answer-key fixtures/v2/answer_key.json.gz --accrual-csv fixtures/v2/invoice_accruals.csv --xlsx outputs/v2/deduction_resolution_workbench_v2.xlsx --metrics-json outputs/v2/evaluation_metrics.json
```

The final workbook must be visually inspected. Keep the public workflow,
fixtures and repository synthetic-only, and do not publish or activate anything
without explicit user instruction.
