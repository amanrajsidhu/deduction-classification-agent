# Deduction Resolution Workbench

Turn retailer deduction and accrual exports into a ranked finance worklist that
shows what matched, what has sufficient ledger support, and what a person must
investigate next.

This repository is a public, synthetic demonstration. It shows a controlled
automation pattern; it is not a hosted product, an accounting authority, or
evidence of production accuracy.

## Who it helps

- **Daily user:** a deductions or accounts-receivable analyst.
- **Executive reader:** a Financial Controller or Finance Director.
- **Best-fit setting:** a consumer-products finance team processing recurring
  retailer or marketplace settlement deductions.

The analyst receives a value-ranked worklist with an explanation and next action
for every line. The finance leader receives a summary of value resolved, value
still exposed, and the controls behind the result.

## The problem

A retailer may pay less than the invoiced amount and attach a cryptic reference.
Finance then has to determine whether the deduction matches an existing accrual,
which configured category it belongs to, whether supporting balance exists, and
what needs investigation.

ERPs and deduction-recovery platforms already address parts of this problem.
This workbench demonstrates the difficult last-mile pattern: resolve clean cases,
constrain uncertain classification with ledger evidence, and make exceptions
visible without treating AI as an accounting decision-maker.

## What the workbench does

1. **Validates the exports.** Dates, amounts, identifiers and counterparties are
   checked before matching. Invalid rows stop as data-quality issues.
2. **Matches clean cases deterministically.** Exact-value, near-date,
   same-counterparty accruals are assigned globally and one-to-one. These cases
   never need an AI classification.
3. **Applies finance configuration before AI.** Approved reference aliases take
   priority. When no alias exists, Claude may propose one configured category or
   abstain as `Unresolvable`.
4. **Allocates supporting evidence once.** An accepted category must have an
   eligible same-counterparty programme balance in the same bucket, within the
   date window and with sufficient remaining value. Consumed balance cannot be
   reused indefinitely.
5. **Fails closed.** Conflicts, missing evidence, exhausted balances and malformed
   model output go to a person rather than a confident-looking answer.
6. **Produces the decision aid.** The Excel workbook begins with monetary
   outcomes and the next investigation, followed by the detailed audit trail.

The system proposes and checks. A person remains responsible for journals,
write-offs, disputes, approvals and every decision of record.

## What the user receives

- A finance-first summary of total, resolved and human-work value.
- A priority worklist ordered by financial exposure.
- Separate views for deterministic matches, supported classifications,
  unresolved lines and data-quality issues.
- The reason, source evidence, balance movement, owner and next action for each
  route.
- Recomputable metrics and a clear result: `Ready for Demo`, `Needs Repair` or
  `Incomplete Run`.

## Verified synthetic demonstration

The complete 250-line fixture produced:

| Outcome | Lines | Value |
|---|---:|---:|
| Auto-matched deterministically | 150 | £87,737.48 |
| Classified with allocated evidence | 75 | £42,555.61 |
| Needs review | 0 | £0.00 |
| Unresolvable from supplied data | 25 | £3,460.10 |
| Data-quality issue | 0 | £0.00 |
| **Total** | **250** | **£133,753.19** |

Every seeded line was routed exactly once. The separate, source-bound evaluator
recomputed the transaction pairs, category outcomes, source eligibility and
balance chains and returned **Ready for Demo** with zero unsafe terminal
misroutes.

That statement has an important limit: all 75 accepted classifications came
from deterministic configured aliases. No AI-proposed category was accepted in
this fixture. The AI's accepted contribution was 25 abstentions, which the
conflict check confirmed as unresolvable from the supplied synthetic data.
Therefore, 100% accepted-classification precision is **not** 100% AI accuracy.

## Why it is designed this way

- **Rules first:** predictable matching should not consume model calls.
- **AI for bounded ambiguity:** the model proposes inside a configured category
  set; it cannot create accounting policy.
- **Ledger evidence over confidence:** a high model score cannot replace an
  eligible source balance.
- **Human authority:** uncertainty creates a work item, not an automated posting.
- **Source-bound evaluation:** the evaluator independently checks the raw
  counterparty, date, bucket, intended synthetic support and balance chain.
- **Synthetic and local:** the public proof does not require prospect data or a
  hosted upload.

## How the build improved

The original demonstration exposed useful controls but its evaluation overstated
one result and treated bucket-level plausibility as evidence. The current
workbench corrects that by:

- separating unresolvable precision from recall;
- canonicalising known counterparty aliases consistently;
- allocating programme balances across the whole run;
- treating missing files and duplicate identities as failures;
- independently rebinding accepted evidence to the raw source rules; and
- presenting monetary outcomes and human actions before technical metrics.

The preserved original workflow and outputs are historical regression evidence,
not the supported implementation and should not be imported or run. The curated
engineering account is in [Build notes](docs/BUILD_NOTES.md); raw internal build
and reasoning logs are deliberately excluded from Git.

## Repository map

```text
fixtures/v2/                  reproducible synthetic inputs and sealed answer key
outputs/v2/                   verified branch results, metrics and workbook
scripts/deduction_rules.py    canonical control rules
scripts/finalize_run.py       exact source-to-output coverage check
scripts/generate_xlsx_output.py source-bound evaluator and workbook builder
scripts/upgrade_workflow_v2.py reproducible workflow builder
tests/                        control, evaluation and publication-boundary tests
workflows/DEDUCTION_RESOLUTION_WORKBENCH_V2.json current portable workflow
outputs/ and workflows/...V1...json historical regression evidence; do not run
docs/                         contract, evidence, risks, dataset and security notes
```

## Verify locally

```bash
python -m pip install -r requirements.txt
python scripts/generate_dataset.py
python scripts/upgrade_workflow_v2.py
python -m unittest discover -s tests -v
python scripts/finalize_run.py \
  --outputs-dir outputs/v2 \
  --settlement-csv fixtures/v2/settlement_deductions.csv
python scripts/generate_xlsx_output.py \
  --outputs-dir outputs/v2 \
  --answer-key fixtures/v2/answer_key.json.gz \
  --accrual-csv fixtures/v2/invoice_accruals.csv \
  --xlsx outputs/v2/deduction_resolution_workbench_v2.xlsx \
  --metrics-json outputs/v2/evaluation_metrics.json
```

These checks require no AI key and do not call Anthropic. Continuous integration
uses Python 3.12 for the byte-reproducibility check.

## Run locally in n8n

The portable workflow export is inactive, unavailable over MCP and contains no
live credential, workflow or instance identifiers. After import, the operator
must attach an authorised Anthropic credential and ensure the configured
`/files/deduction-workbench/v2/` paths are mapped to an appropriate local Docker
volume. Use synthetic inputs and execute it manually.

## Security and limitations

Do not upload real settlement exports, ledgers, invoices, customer details or
portal credentials to this public demonstration. Real-data work requires a
separately authorised client environment with agreed access, retention and
deletion controls.

The repository does not claim production accuracy, time saved, recovered
revenue, compliance certification, buyer willingness to pay or superiority over
established deduction platforms. See the [security boundary](docs/SECURITY_AND_DATA_BOUNDARY.md),
[evaluation standard](docs/01_EVALUATION.md), [evidence note](docs/02_EVIDENCE_AND_POSITIONING.md)
and [risk register](docs/03_RISK_REGISTER.md).
