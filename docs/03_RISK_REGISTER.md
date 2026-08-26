# Risk register and stop conditions

| Risk | What could go wrong | Control in this build | Stop condition |
|---|---|---|---|
| Misleading metrics | Recall is reported as accuracy again, or a denominator is hidden. | Machine-readable metrics, full confusion matrix, named denominators and regression tests on the V1 defect. | Any public number cannot be recomputed from committed synthetic files. |
| Missing output | A failed branch is presented as zero records. | Every branch is required; empty branches can only be materialised after exact ID coverage is proven. | Duplicate, unknown or omitted input ID. |
| False ledger authority | A bucket-level coincidence is presented as transaction proof. | V2 calls the evidence a programme-balance allocation, records before/after balance and never claims document-level proof. | Accepted line lacks a reconciling allocation or sufficient balance. |
| Balance reuse | Each AI batch starts from the full balance and overspends it. | Evidence allocation runs once after all model batches finish. | Any balance after allocation is negative or does not reconcile. |
| Transaction evidence reuse | One transaction accrual is reported as support for multiple auto-matches. | Source-bound evaluator requires one known transaction-scope accrual per auto-match and exact one-time use. | Any matched source ID is blank, unknown, wrong-scope or reused. |
| Malformed source input | An impossible date, numeric prefix or duplicate ledger ID is interpreted as valid evidence. | Full-string amount grammar, calendar round-trip, finite date comparisons, unique-ID gate and source-ledger reconciliation. | Any malformed value reaches an accepted terminal outcome. |
| Spreadsheet formula injection | A source or model string becomes an executable formula when the workbook opens. | One sink-side literal-text guard covers all record-derived detailed and worklist cells; intended builder formulas remain explicit. | Any record-derived cell loads with formula type. |
| Model variance | Borderline lines change between runs. | Deterministic stages dominate; structured output; safe-stop routing; V2 paid run must be repeated before publishing headline model metrics. | Headline result moves by more than two percentage points across three runs. |
| Synthetic overconfidence | Perfect fixture results are repeated as production accuracy. | Dataset card and same-context caveat in public claims. | Any CopyWise content repeats a score without the synthetic limitation. |
| Sensitive data | Someone sends a real ledger to the public demo. | Synthetic-only boundary and separately authorised client path. | Any real company data reaches the repo, public demo or unapproved channel. |
| Competitive overstatement | Positioning implies the workbench replaces established products. | Complement positioning and explicit non-goals. | Repeated feedback shows the claimed accounting-side job is already fully served in the target environment. |
| Adoption failure | Finance readers find the workbook technical or irrelevant. | Money-first summary, priority worklist and two-minute outcome narrative. | Three consecutive qualified readers cannot explain the benefit after viewing it. |
| Scope creep | Portal integration, SaaS hosting or multi-retailer breadth delays proof. | Product contract and deferred list. | Work begins on a non-goal before the synthetic V2 run passes. |
| Commercial mismatch | The deduction-heavy segment is inaccessible or outside CopyWise's reachable buyer base. | Treat as a proof asset first; track conversations attributable to it. | Zero qualified deduction conversations after 8–10 weeks of active manual distribution. |

The status **Ready for Demo** means only that the synthetic technical gates pass.
It does not cancel any commercial, security or production risk in this register.
