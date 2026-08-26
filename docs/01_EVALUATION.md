# Evaluation standard

The public demo is graded against a synthetic sealed answer key. That makes the
run recomputable; it does not make the result representative of production.

## Metrics and denominators

- **Auto-match precision:** seeded matchable lines routed to Auto-matched / all
  lines routed to Auto-matched.
- **Auto-match recall:** seeded matchable lines routed to Auto-matched / all
  seeded matchable lines.
- **Pair correctness:** correct accrual IDs / all auto-matched pairs.
- **Transaction-match source integrity:** every auto-match references one known
  transaction-scope accrual and no source accrual is reused.
- **Classification precision:** correctly bucketed seeded-classifiable lines /
  all lines accepted as Classified with evidence.
- **Classifiable automation coverage:** correctly accepted classifications / all
  seeded-classifiable lines.
- **Source-ledger allocation integrity:** every accepted classification names
  the intended synthetic programme-balance source; the source has the same
  eligible bucket and counterparty, falls within the 45-day window, and supports
  the deduction value; its before/after transitions form one chain from the
  opening balance; and aggregate consumption does not exceed that balance.
- **Unresolvable precision:** genuinely unresolvable lines / all lines labelled
  Unresolvable.
- **Unresolvable recall:** genuinely unresolvable lines found / all genuinely
  unresolvable seeded lines.
- **Terminal misroute:** a line accepted into the wrong final outcome. Needs
  Review and Data-quality Issue are safe stops, not terminal misroutes.

## Known V1 result

The committed V1 outputs route all 250 lines, but nine seeded-matchable Amazon
lines were labelled Unresolvable. Consequently:

- unresolvable recall is 25/25 = 100%;
- unresolvable precision is 25/34 = 73.5%; and
- terminal misroutes are 9 lines, £3,212.35.

This is intentionally retained as a regression fixture. The evaluator must
reproduce the defect before the V2 pipeline is allowed to claim it fixed it.

## Status rules

- **Incomplete Run:** any branch or source-ledger file is missing or invalid, or
  any seeded/source ID is duplicated, unknown or omitted.
- **Needs Repair:** coverage is complete but at least one safety gate fails.
- **Ready for Demo:** coverage is complete, terminal misroutes are zero and all
  published gates pass.

Auto-match recall and classifiable automation coverage are monitoring indicators,
not readiness gates. The workflow is designed to fail closed: a safe stop can
reduce automation coverage without creating an unsafe terminal outcome. Coverage
must still be disclosed so a technically safe but commercially weak run is not
presented as useful automation.

Every public percentage must state what it measures and must retain the
synthetic-data caveat in the same context.
