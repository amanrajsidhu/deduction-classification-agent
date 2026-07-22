# Deduction and exception classification agent

An n8n workflow that takes a settlement file full of cryptic deductions, resolves the clean lines deterministically, uses Claude to classify the leftovers into a company's own accrual buckets, and checks every AI answer against the ledger before trusting it.

This is a demo build on synthetic data. It exists to prove the concept and produce accuracy numbers that can be independently verified, not to be a drop-in production system. The line between the two is spelled out in [Demo vs. production](#demo-vs-production).

---

## The problem

A company that sells physical products through channels it doesn't control (marketplaces like Amazon or Walmart, big-box retail programs, its own storefront's payment stack, third-party processors) gets paid in settlements. The money that arrives is rarely the money that was invoiced. Each settlement comes in net of deductions: amounts withheld for promotions, shortage claims, price disputes, damaged goods, chargebacks.

The deduction line itself usually explains very little. In this dataset, which is modelled on that reality, the single most common description is literally `Miscellaneous deduction - see note`. Reference codes are opaque. The same counterparty shows up under half a dozen names (`Amazon EU SARL`, `AMZN Mktp UK`, `AMAZON.COM LLC`). Some remitters are just `Unknown Remitter`.

Finance teams already accrue for expected deductions in their own buckets, and accounting systems already auto-match the clean cases. The pain is the remainder: lines that match nothing, described too vaguely to bucket without a person digging through statements and portals. At volume, that person falls behind, and unexplained deductions accumulate as unreconciled balance.

This build targets that remainder. Not the matching layer, which is a solved problem, but the classification of what's left after matching.

## What it does

Given a settlement/deductions file and an accruals ledger, the workflow:

1. Normalises every line: vendor names, dates, amounts, plus a stable hash key per line.
2. Matches deterministically. Clean amount/date/vendor matches are resolved without any LLM involvement.
3. Sends the unmatched lines to Claude in batches, to be classified into one of six buckets.
4. Verifies each classification against the ledger. If no supporting accrual exists for the claimed bucket, the line goes to a human instead of being trusted.
5. Routes every line to one of five outcomes and exports a six-tab Excel report.

```
                                                 auto-matched          (deterministic, no LLM)
 CSVs -> normalise -> deterministic match -> --- classified+verified   (LLM agreed with ledger)
                                                 needs review          (LLM and ledger disagreed)
                                                 unresolvable          (genuinely no signal)
                                                 data quality issue    (unparseable input)
```

The design principle: the LLM never gets the last word. A deterministic evidence check sits behind it, so a confident but wrong classification gets caught instead of silently exported.

## Results

The dataset is synthetic and seeded with a known ground truth (a sealed answer key), which is what makes the accuracy numbers checkable rather than claimed. On the canonical run of 250 deduction lines:

| Outcome | Count | Share |
|---|---|---|
| Auto-matched (no LLM) | 141 | 56.4% |
| Classified and verified | 65 | 26.0% |
| Unresolvable (correctly flagged) | 34 | 13.6% |
| Needs review | 10 | 4.0% |
| Data quality issues | 0 | 0.0% |

Scored against the sealed answer key:

- 100% classification accuracy (65 of 65 verified lines matched the true bucket)
- 100% unresolvable-flagging accuracy (all 25 genuinely unresolvable lines were flagged, not guessed)
- 100% auto-match pair correctness, meaning zero false matches across all 141 auto-matched lines
- 94% auto-match recall (141 of 150 seeded matchable lines; the other 9 carry a vendor-name variant that deliberately fails the match threshold and gets handled by the classifier instead)
- 5 Claude API calls in total, roughly 17.3k input and 10.6k output tokens. Deterministic filtering means most lines never reach the LLM at all.

Counts on the borderline cases shift slightly between runs, since the LLM is not bit-for-bit deterministic. The deterministic stages don't move: the auto-match count and the zero-false-match result are stable.

## How it works

Six stages inside the workflow:

1. **Intake.** Reads the two CSVs.
2. **Normalise and key.** Lowercases and strips vendor names, parses dates through a strict priority order (ISO, unambiguous day/month formats, Excel serials; genuinely ambiguous dates get flagged rather than guessed), and computes an FNV-1a key per line.
3. **Deterministic match.** Ranks all valid settlement-to-accrual pairs globally and assigns best first, each accrual consumable once. Amounts are compared in integer pence to avoid floating-point tolerance bugs. Thresholds: amount within £0.01, date within 1 day, vendor score of at least 60.
4. **Classify.** Unmatched lines go to Claude in batches, using forced tool-use with a strict schema so the response arrives as parsed JSON rather than free text that has to be scraped. A malformed or failed batch degrades to "needs review" instead of crashing the run.
5. **Verify against evidence.** The check that makes the AI usable: does a supporting accrual exist for the claimed bucket, within amount and date tolerance? An "unresolvable" call from the model can only be overridden if the ledger holds a plausible accrual with a matching vendor. Agreement passes; disagreement goes to a human.
6. **Route and export.** Five outcome branches, each written to JSON, then compiled into the six-tab XLSX.

The bugs found while building this, and how they were fixed, are written up in [`docs/BUILD_NOTES.md`](docs/BUILD_NOTES.md). That file is the substance of the project; the short version is that three of the five interesting failures only appeared when real data ran at real scale.

## Demo vs. production

Two parts of this repo are demo scaffolding and would not exist in a client deployment:

**The sealed answer key** (`outputs/answer_key.json.gz`). It exists only to grade the demo. It is fully synthetic, generated deterministically by `scripts/generate_dataset.py` with a fixed seed, and the workflow itself never reads it. It gets used once, afterwards, by a separate script that compares the workflow's output against ground truth. Real client data has no answer key, so in production this concept disappears entirely.

**The Python scoring script** (`scripts/generate_xlsx_output.py`). It runs outside the automation and does two jobs: grading against the answer key, and building the Excel report. In production, the grading half disappears for the reason above, and the report-building half moves inside the n8n workflow as a final step, so the report is produced automatically with no external script.

Everything else (the pipeline, the deterministic matcher, the batched classification, the evidence verification) is the real mechanism, demonstrated on synthetic data.

## Repo structure

```
.
├── README.md
├── workflows/
│   └── ...DEDUCTION_CLASSIFICATION...json   # the n8n workflow (import this)
├── scripts/
│   ├── generate_dataset.py                  # builds the synthetic dataset + sealed answer key
│   └── generate_xlsx_output.py              # scores results + builds the six-tab XLSX (demo-side)
├── outputs/
│   ├── settlement_deductions.csv            # input: the deductions
│   ├── invoice_accruals.csv                 # input: the accruals ledger
│   ├── answer_key.json.gz                   # sealed ground truth (synthetic)
│   ├── auto_matched.json, ...               # workflow output, one file per branch
│   └── deduction_classification_output.xlsx # the final six-tab report
└── docs/
    └── BUILD_NOTES.md                       # the engineering story
```

## Running it yourself

1. Regenerate the dataset if you want to (the committed files are identical, the generator is seeded):
   ```bash
   python scripts/generate_dataset.py
   ```
2. Import the workflow JSON from `workflows/` into an n8n instance, point the file nodes at the two CSVs, and attach an Anthropic credential. Running it produces the per-branch JSON output files.
3. Score the output and build the report:
   ```bash
   python scripts/generate_xlsx_output.py
   ```
   This reads the workflow's JSON output plus the answer key and writes `outputs/deduction_classification_output.xlsx`.

## Stack

- n8n for orchestration, self-hosted locally in Docker during development
- Claude (Anthropic API) for exception classification, via forced tool-use
- Python with openpyxl for dataset generation and scoring
- The workflow itself was built agentically: Claude Code driving n8n's MCP server under human direction, on top of internal build conventions. The process is described at the end of [`docs/BUILD_NOTES.md`](docs/BUILD_NOTES.md).

---

*Built as a proof-of-work demo. All data in this repo is synthetic. No real company, customer, or transaction data appears anywhere.*
