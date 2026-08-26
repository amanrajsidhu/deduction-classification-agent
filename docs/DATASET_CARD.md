# Synthetic dataset card

## Purpose

The dataset tests a controlled retailer-deduction workflow without exposing any
company, customer or transaction data. Transaction records, identifiers and
values are generated. Recognisable public retailer/platform names are used only
as illustrative counterparties; they do not describe real transactions.

## Current canonical V1 fixture

- 250 settlement deductions.
- 150 seeded as deterministically matchable.
- 75 seeded as classifiable from descriptions and reference codes.
- 25 seeded as genuinely unresolvable from supplied fields.
- Currency and accounting labels are illustrative, not accounting guidance.

## V2 fixture

- The same 250-line split is generated under seed 42.
- 150 dedicated transaction accruals support deterministic one-to-one matches.
- 24 programme-level balances support the counterparty/bucket combinations used
  by the 75 classifiable lines, with 10% synthetic headroom.
- Every classifiable answer-key entry names its intended programme balance.
- `evidence_scope` prevents programme balances from entering exact matching.
- Under the CI-pinned Python 3.12 runtime, the CSV and compressed answer key are
  byte-for-byte reproducible.

## What it can test

- Stable one-to-one matching.
- Routing coverage and duplicate detection.
- Classification against known synthetic labels.
- Whether the system abstains on deliberately vague lines.
- Whether evaluation metrics are calculated honestly.

## What it cannot prove

- Production accuracy or generalisation to a real retailer.
- Correctness of a client's accounting treatment.
- Availability or quality of portal documentation.
- Time saved, recovery achieved or willingness to pay.
- Compliance with a client's control framework.

The answer key is used only by the external evaluator. The n8n workflow does not
read it.

The committed V1 files are a frozen regression baseline. The current generator
creates the V2 fixture; it does not regenerate the historical V1 evidence.
