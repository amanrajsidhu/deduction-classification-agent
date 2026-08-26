# Build notes: what the first evaluation revealed

This project began as a technically plausible deduction-classification demo. Its
current implementation is more valuable because the evaluation found that two of its
strongest trust claims were not supported by its own evidence.

## Why deductions

Clean transaction matching is not the interesting part. Finance teams struggle
with the residue: cryptic deduction lines that require classification, supporting
documents and a decision about what a person should investigate next.

The design therefore keeps deterministic matching first and spends AI calls only
on exceptions. It is deliberately a complement to ERPs and recovery platforms,
not an attempt to recreate them.

## What the original build did well

- Global best-first, one-to-one deterministic matching.
- Integer-pence comparisons rather than fragile floating-point thresholds.
- Forced structured model output with schema validation.
- Malformed model output degraded to human review rather than disappearing.
- Synthetic data with a sealed answer key.
- Per-branch exports and a human-review outcome.
- Token usage deduplicated by API response ID.

These remain the foundation of the current workbench.

## What the recomputation found

### 1. Recall had been called accuracy

V1 found every one of the 25 genuinely unresolvable lines. That is 100% recall.
But it labelled 34 lines unresolvable, and nine of those were actually seeded as
matchable. Precision was therefore 25/34, or 73.5%.

Those nine lines were all `AMZN Mktp UK` against `Amazon`. The fixture generator
and workflow used different similarity ideas, so the generator considered the
pairs valid while the workflow gave them zero token overlap. The same mismatch
then prevented the safety path from rescuing them.

The nine unsafe terminal routes were worth £3,212.35.

### 2. The ledger check was plausibility, not evidence

The normal V1 check asked only whether any unused accrual existed in the proposed
bucket within 45 days and within a 0.25x–4x amount band. It did not require the
same vendor and did not consume or allocate balance.

Consequently, 65 accepted classifications drew repeatedly on a very small pool
of leftover accruals. The fixture had not seeded supporting evidence for those
75 classifiable lines at all. The check could show that a bucket contained
something vaguely plausible; it could not show that the deduction was supported.

### 3. The status ignored the broken parts

The old workbook based its overall label only on accepted-classification
accuracy. If no classifications were accepted, it substituted 100% and could
still report Excellent. The status ignored routing precision, omitted lines,
missing files and false-unresolvable outcomes.

### 4. A missing file became a clean zero

The report loader converted an absent branch file into an empty list. The
committed data-quality output was missing, yet the workbook published zero
data-quality issues without marking the run incomplete.

## Current repair

### One counterparty identity

The current build adds explicit canonical identities for the five synthetic channels. Amazon,
`AMZN` and `Mktp` variants resolve to the same identity. The fixture generator
and workflow carry the same `2.0.0` ruleset marker, and tests lock the expected
aliases.

Configured reference aliases are also deterministic. For example,
`OTHER-DEDUCT-*` maps to `Chargeback/Other` before the model proposal can affect
the accepted bucket. The output records whether a bucket came from a configured
alias or an AI proposal.

### Separate transaction matches from programme evidence

The current fixture contains:

- dedicated transaction accruals for the 150 exact-match cases; and
- programme-level accrual balances for classifiable deduction populations,
  grouped by counterparty and bucket with documented headroom.

The answer key identifies the intended supporting programme balance, making the
control path testable instead of coincidental.

### Allocate once across the whole run

The n8n loop still sends exceptions to the model in batches, but evidence is no
longer checked inside each batch. Parsed results return to the loop; only when all
batches have finished does the evidence node receive the complete population.

It then sorts deterministically, finds a same-counterparty programme balance in
the proposed bucket, confirms sufficient available value and decrements that
balance. The output records allocated amount, balance before and balance after.
An exhausted balance cannot be reused.

### Fail closed

- Impossible calendar dates, malformed numeric strings, zero values and missing
  or duplicate IDs cannot enter matching. Invalid settlement rows become Data
  Quality; invalid accrual identity stops the ledger run.
- Insufficient balance or no same-counterparty programme evidence: Needs Review.
- Malformed or missing model classification: Needs Review.
- Model proposes Unresolvable while a same-counterparty exact-amount near-date
  ledger candidate exists: Needs Review.
- No same-counterparty exact-amount near-date candidate: Unresolvable from
  supplied data, with an explicit limitation rather than a claim of accounting
  truth.

### Make incompleteness visible

Every branch file is required. `finalize_run.py` may create an explicit empty
array only after it proves that every input deduction ID already appears exactly
once across the existing branch exports. Missing or duplicate coverage stops the
process.

The live workflow now also writes all five branch files at the end of every run,
including explicit empty arrays. This prevents a non-empty file from a previous
run being mistaken for a current result.

### Lead with finance outcomes

The workbook starts with:

- total deduction value;
- value resolved without manual work;
- value requiring a person;
- value in unsafe terminal routes;
- the first line to investigate; and
- a ranked worklist with owner, status and next action.

The full confusion matrix and metric denominators remain visible on the
Evaluation tab.

Record-derived workbook text is written as inert text, so a source or model
string beginning with a spreadsheet formula marker cannot execute as a formula.
The evaluator also loads the authoritative accrual CSV, requires unique source
IDs, and proves that every accepted classification consumes one valid programme
balance chain without exceeding its opening value.

## Tests that now gate the build

The local suite and CI check:

- the V1 evaluator reproduces 73.5% unresolvable precision and nine terminal
  misroutes;
- a missing file cannot become a zero;
- zero accepted classifications cannot receive a positive status;
- the V2 fixture is byte-for-byte reproducible;
- alias variants share the intended identity;
- classifiable lines do not accidentally meet deterministic match conditions;
- a complete 75-line allocation never drives a programme balance negative;
- duplicate or blank accrual identities stop allocation;
- impossible dates and malformed amounts fail in the embedded n8n JavaScript;
- aggregate allocations reconcile to one unique source-ledger balance;
- every deterministic match references one known transaction accrual exactly
  once, even when the pair-correctness percentage would otherwise round above
  its threshold;
- source/model formula-like strings remain inert in both detailed tabs and the
  priority worklist;
- the workflow allocates only after all model batches finish;
- the permissive V1 amount multiplier is absent; and
- empty branch materialisation is refused until routing coverage is exact;
- public workflow exports contain no live instance, workflow or credential
  identifiers and remain inactive/unavailable over MCP; and
- the workflow contains a final complete five-branch export stage.

## Verified synthetic run — 25 August 2026

The supported workbench completed the full 250-line synthetic fixture. Live
workflow and execution identifiers are deliberately omitted from the public
repository. The final manifest reconciled every input ID exactly once:

- 150 auto-matched;
- 75 classified with a sufficient allocated programme balance;
- 0 needs review;
- 25 unresolvable from the supplied data; and
- 0 data-quality issues.

The sealed-key evaluator returned **Ready for Demo**: 100% pair correctness,
100% accepted classification precision, 100% allocation coverage, 100%
source-ledger allocation integrity, 100% unresolvable precision, 100%
unresolvable recall and zero unsafe terminal misroutes. These are fixture-specific
results, not production accuracy.

All 75 accepted classifications in this run came from configured reference
aliases, not AI proposals. The AI's accepted contribution was 25 abstentions that
the deterministic conflict check confirmed as unresolvable from the supplied
data. Classification precision measures every accepted classification and must
not be presented as AI accuracy. Auto-match recall and classifiable automation
coverage are disclosed monitoring indicators rather than readiness gates, because
a safe stop can reduce coverage without creating an unsafe terminal route.

Fixture byte reproducibility is verified under the CI-pinned Python 3.12 runtime.
The committed V1 evidence is a frozen regression baseline; the current generator
produces V2 and does not recreate V1.

The workflow export remains inactive and uses only portable `/files` paths. The
operator is responsible for mapping those paths to an appropriate local Docker
volume before a manual synthetic run.

## Publication hardening — 26 August 2026

The public release boundary was tightened after the verified run:

- the evaluator now recomputes bucket, raw counterparty, raw date-window and
  intended synthetic support eligibility before treating an allocation as valid;
- source and routed deduction identifiers must be present, string-valued and
  unique before a manifest can be complete;
- provider response identifiers were replaced with local batch references while
  preserving aggregate usage accounting;
- public-boundary tests reject credentials, live workflow identifiers and
  provider response identifiers;
- the README now leads with the user, problem, outcome and authority boundary;
  and
- the original workflow is labelled as historical regression evidence, not a
  supported import.

The raw internal build log, local operator context and private reasoning remain
outside Git. This document is the deliberately curated public engineering story.

## What is not claimed

The repository does not claim production
accuracy, time saved, recovered revenue or willingness to pay. Those outcomes
require an authorised real engagement and separately designed measurement.
