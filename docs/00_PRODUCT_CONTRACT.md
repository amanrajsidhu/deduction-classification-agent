# Product contract

## Decision

This repository will become the **Deduction Resolution Workbench**. It remains
a public, synthetic proof asset and a service wedge. It is not a hosted product,
an accounting authority, or a substitute for enterprise deduction platforms.

## First user and reader

- **User:** the deductions or accounts-receivable analyst who investigates
  retailer settlement deductions.
- **Executive reader:** the Financial Controller or Finance Director who needs
  to understand the value resolved and the value still exposed.

## Job to be done

For each settlement cycle, turn a deductions CSV and an accrual-ledger CSV into
one value-ranked worklist showing:

1. what deterministic rules resolved;
2. what AI classified and a ledger balance safely supported;
3. what requires a person;
4. what cannot be resolved from the supplied data; and
5. why every line was routed that way.

## Product promise

The workbench reduces manual sorting. It does **not** make an accounting
decision. Rules match clean lines, AI proposes a bucket only for the remainder,
and deterministic controls either allocate supporting evidence or stop the line
for human review.

## Inputs

- Settlement/deductions CSV.
- Accrual-ledger CSV using the finance team's configured bucket names.
- Public demonstration: synthetic data only.

## Outputs

- One workbook beginning with monetary outcomes and the next investigation.
- Ranked priority worklist with owner, status and next action.
- Evidence and reasoning on every accepted or stopped classification.
- Full confusion matrix, precision, recall, coverage and value-weighted errors.
- Machine-readable evaluation JSON.

## Authority and human responsibility

The workbench has no professional authority of its own. Its recommendations are
credible only to the extent that the disclosed matching rules, allocated ledger
evidence and evaluation support them. A person retains responsibility for
journals, write-offs, disputes, approvals and any decision of record.

## Acceptance gates

A run may be labelled **Ready for Demo** only when:

- all expected branch exports exist and every seeded line is routed exactly once;
- there are zero unsafe terminal misroutes;
- auto-match pair correctness is at least 99%;
- accepted classification precision is at least 95%;
- unresolvable precision and recall are each at least 95%; and
- every accepted classification carries allocated evidence with sufficient
  available balance.

Missing outputs produce **Incomplete Run**, never a zero count. No accepted
classifications produces **Not Assessable** or **Needs Repair**, never Excellent.

## Non-goals

- No journals, write-offs, disputes or approvals.
- No retailer-portal or ERP integration in the public build.
- No hosted SaaS and no real prospect data.
- No claim to replace HighRadius, SupplyPike/SPS Commerce or ERP-native tooling.
- No outreach or LinkedIn automation.

## Phased value

1. Honest evaluation and repeatable tests.
2. Alias-safe matching and balance-aware evidence allocation.
3. Finance-first workbook and priority worklist.
4. Public synthetic demo, short video and outcome-led content.
5. Live integrations only inside a separately authorised client engagement.
