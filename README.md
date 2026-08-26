# Deduction Resolution Workbench

A public, synthetic demonstration of a controlled finance-automation pattern:
rules resolve clean retailer deductions, AI proposes categories for the
remainder, ledger balances constrain what can be accepted, and uncertain lines
stop for a person.

> **Current status:** V2 has been run end to end in the local n8n instance on
> the 250-line synthetic fixture. The complete run passed the independent
> evaluator as **Ready for Demo**. This is synthetic technical
> evidence, not production accuracy or approval for real client data.

## The 12-year-old explanation

A retailer sometimes pays a supplier less than the invoice and attaches a
confusing note explaining why. A finance analyst then has to work out which
deductions were expected, which accounting bucket they belong in, and which
ones need more information.

This workbench sorts the clear cases, proposes an answer for the harder cases,
checks that the relevant accrual balance can support that answer, and puts
anything unsafe into a human worklist—starting with the largest amounts.

## Who it helps

- **Daily user:** deductions or accounts-receivable analyst.
- **Executive reader:** Financial Controller or Finance Director.
- **Best-fit context:** a consumer-products finance team processing recurring
  retailer or marketplace settlement deductions.

The analyst gets a ranked worklist. The finance leader gets a value-led summary
showing what was resolved, what remains exposed and why.

## The problem it addresses

Retailer deduction lines are frequently cryptic. Counterparty names vary,
reference codes are opaque and the supporting information may sit across an ERP,
a retailer portal and spreadsheets. Clean matches are not the hard part. The
problem is the residue that has to be classified, evidenced and investigated.

This repository demonstrates that residue-handling pattern. It complements
deduction-recovery products and ERPs; it does not claim to replace them.

## How V2 works

1. **Validate and normalise.** Dates, amounts and counterparty names are parsed.
   Known aliases such as `AMZN Mktp UK` and `Amazon` share one canonical identity.
2. **Match deterministically.** Exact-value, near-date, same-counterparty pairs
   are assigned globally and one-to-one. These lines never reach AI.
3. **Apply controlled aliases, then constrain the AI proposal.** Approved
   reference aliases take priority. When no alias exists, Claude proposes one
   configured bucket or abstains as `Unresolvable`.
4. **Allocate ledger evidence once across the full run.** An accepted proposal
   must have a same-counterparty programme accrual in the proposed bucket with
   enough available balance. The allocation reduces that balance, preventing
   one accrual from being reused indefinitely.
5. **Fail closed.** Conflicts, exhausted balances, malformed model output and an
   `Unresolvable` proposal with an exact-amount near-date ledger candidate stop
   for human review.
6. **Report money and next actions.** The workbook begins with value resolved,
   value requiring a person, unsafe-routing exposure and the first item to
   investigate.

The system proposes. A person retains responsibility for journals, write-offs,
disputes, approvals and every decision of record.

## What the V1 audit found

V1 looked stronger than it was. The new evaluator recomputes the canonical
250-line run as follows:

| Outcome | Lines | Value |
|---|---:|---:|
| Auto-matched | 141 | £84,525.13 |
| Classified using V1's bucket-plausibility check | 65 | £47,461.98 |
| Needs review | 10 | £1,733.51 |
| Labelled unresolvable | 34 | £6,325.43 |
| **Total** | **250** | **£140,046.05** |

The important correction is not hidden:

- all 25 truly unresolvable lines were found: **100% recall**;
- only 25 of the 34 lines labelled unresolvable were truly unresolvable:
  **73.5% precision**;
- nine matchable Amazon lines worth **£3,212.35** were accepted into the wrong
  terminal outcome; and
- the 65 accepted classifications reused a small set of leftover accruals under
  a permissive bucket-level check. That demonstrated plausibility, not allocated
  evidence.

The preserved V1 evidence therefore says **Needs Repair**, not Excellent. See
[`docs/01_EVALUATION.md`](docs/01_EVALUATION.md) for every denominator and status
gate, and [`docs/02_EVIDENCE_AND_POSITIONING.md`](docs/02_EVIDENCE_AND_POSITIONING.md)
for the conversation, market and competitor evidence with its limitations.

## What V2 changes

- One alias rule set across fixture generation and workflow matching.
- A separate programme-balance population for classifiable deductions.
- Available-balance allocation across the complete run, after all AI batches.
- Exact-amount near-date conflicts forced to human review.
- Required branch files and exact ID coverage before a run can be complete.
- Full confusion matrix, precision, recall, coverage and value-weighted errors.
- Finance-first workbook with a priority worklist, owner, status and next action.
- Reproducible fixtures, adversarial regression/control tests and continuous integration.

## Verified V2 result

The 25 August 2026 full synthetic run produced:

| Outcome | Lines | Value |
|---|---:|---:|
| Auto-matched deterministically | 150 | £87,737.48 |
| Classified with allocated evidence | 75 | £42,555.61 |
| Needs review | 0 | £0.00 |
| Unresolvable from the supplied data | 25 | £3,460.10 |
| Data-quality issue | 0 | £0.00 |
| **Total** | **250** | **£133,753.19** |

Every seeded line was routed exactly once. Pair correctness, accepted
classification precision, evidence-allocation coverage, unresolvable precision
and unresolvable recall were all 100% on this controlled fixture, with zero
unsafe terminal misroutes. The evaluator's conclusion is **Ready for Demo**.
Those figures describe this synthetic answer key only.

The classification result needs one important qualification: all 75 accepted
classifications came from deterministic, configured reference aliases. No AI
proposal was accepted as a classification in this fixture. The AI's accepted
contribution was to abstain on 25 deliberately vague lines, which the conflict
check then confirmed as unresolvable from the supplied data. The 100%
classification-precision result therefore measures all accepted classifications;
it must not be presented as 100% AI accuracy.

Auto-match recall and classifiable automation coverage are reported as monitoring
indicators, not **Ready for Demo** gates. A safe stop can reduce coverage without
creating an unsafe terminal result.

## Repository map

```text
fixtures/v2/                  reproducible V2 synthetic inputs and sealed key
outputs/                      preserved V1 baseline evidence
outputs/v2/                   verified V2 branches, manifest, metrics and workbook
scripts/deduction_rules.py    canonical Python control rules used by tests
scripts/generate_dataset.py   deterministic V2 fixture generator
scripts/finalize_run.py       proves exact coverage before creating empty branches
scripts/generate_xlsx_output.py strict evaluator and workbook builder
scripts/upgrade_workflow_v2.py deterministic V1-to-V2 workflow builder
tests/                        evaluation, fixture, allocation and workflow tests
workflows/...V1...json        preserved baseline workflow
workflows/DEDUCTION_RESOLUTION_WORKBENCH_V2.json  V2 workflow
docs/                         contract, evaluation, dataset and security boundary
```

## Verify locally

```bash
python -m pip install -r requirements.txt
python scripts/generate_dataset.py
python scripts/upgrade_workflow_v2.py
python -m unittest discover -s tests -v
python scripts/generate_xlsx_output.py \
  --outputs-dir outputs/v2 \
  --answer-key fixtures/v2/answer_key.json.gz \
  --accrual-csv fixtures/v2/invoice_accruals.csv \
  --xlsx outputs/v2/deduction_resolution_workbench_v2.xlsx \
  --metrics-json outputs/v2/evaluation_metrics.json
```

These commands require no AI key. They prove fixture reproducibility, alias
behaviour, allocation safety, workflow structure and source-ledger-bound V2
evaluation. They do not execute n8n or call Anthropic.

Continuous integration pins Python 3.12. The byte-for-byte fixture reproducibility
claim applies to that pinned runtime.

## Re-run V2 in n8n

The local workflow is `Deduction Resolution Workbench V2` and remains inactive.
The public export contains no live workflow, instance or credential identifiers;
select the intended n8n credential after import. Its dedicated Docker file volume is
mounted at `/files`; no input or output is stored inside n8n's protected settings
directory.

1. Copy the two fixture CSVs into
   `/files/deduction-workbench/v2/input/`.
2. Confirm the existing Anthropic credential is attached and run the workflow
   manually.
3. Copy the five JSON branch exports into `outputs/v2/`.
4. Prove routing coverage and materialise any genuinely empty branch:

   ```bash
   python scripts/finalize_run.py
   ```

5. Evaluate V2 without overwriting the V1 baseline:

   ```bash
   python scripts/generate_xlsx_output.py \
     --outputs-dir outputs/v2 \
     --answer-key fixtures/v2/answer_key.json.gz \
     --accrual-csv fixtures/v2/invoice_accruals.csv \
     --xlsx outputs/v2/deduction_resolution_workbench_v2.xlsx \
     --metrics-json outputs/v2/evaluation_metrics.json
   ```

A result may be called **Ready for Demo** only if the complete run has zero
unsafe terminal misroutes and passes every published precision and evidence gate.

## Data and security boundary

Everything committed here is synthetic. Do not send, request or upload real
settlement exports, ledgers, invoices, customer details or portal credentials to
the public demo. Real-data work requires a separately authorised client
environment and agreed access, retention and deletion controls. See
[`docs/SECURITY_AND_DATA_BOUNDARY.md`](docs/SECURITY_AND_DATA_BOUNDARY.md).

## Non-goals

- No automatic journal posting, write-off, dispute or approval.
- No retailer-portal or ERP integration in the public repository.
- No hosted SaaS and no production-accuracy claim.
- No claim to replace enterprise deduction platforms.
- No automated LinkedIn or outreach activity.

The value of this repository is the visible reasoning: a useful finance workflow,
measurable controls, honest failure disclosure and a repair that can be rerun.
The ways this could still fail are recorded in
[`docs/03_RISK_REGISTER.md`](docs/03_RISK_REGISTER.md).
