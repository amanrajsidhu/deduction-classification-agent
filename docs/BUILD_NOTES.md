# Build notes

The engineering story behind this build: the decisions that mattered and the bugs that were real. These are things that actually broke during development and how they got fixed, not a tidied-up retrospective. If you're evaluating the work, read this file.

## Why classification, not matching

The first instinct on a problem like this is to build a reconciliation tool. That was rejected early. Matching clean transactions is a solved problem; accounting systems already do it well. The unsolved part is everything that fails to match: exception lines that need judgement to bucket correctly. So the build puts a deterministic matcher up front to clear the easy majority, and spends LLM calls only on the remainder.

This also keeps cost and latency down. On the demo run, 141 of 250 lines never reach the model.

## The dataset is seeded on purpose

A demo that classifies data it also authored proves nothing. So the synthetic dataset is generated with a sealed answer key and a deliberate three-way split:

- roughly 60% cleanly matchable, resolving without the LLM
- roughly 30% classifiable from line evidence, which is the LLM's actual job
- roughly 10% genuinely unresolvable, where the correct answer is "cannot be determined from this data alone"

The last class is the one that matters. It's easy to build a system that always guesses a bucket and looks confident doing it. The harder bar is flagging the unresolvable lines as unresolvable instead of guessing, so the workflow is scored on that explicitly.

## Deterministic matching: two real bugs

The matcher looked simple and wasn't.

**Order-dependent greedy matching.** The first version walked settlement rows in file order and let each one grab its best available accrual. On tie-scores, an earlier row could take an accrual that a later row had a stronger claim to. Fixed by ranking all valid candidate pairs globally and assigning best to worst, with each accrual consumable only once.

**Floating-point tolerance.** The amount tolerance was £0.01. In floating point, `2502.19 - 2502.18` evaluates to `0.010000000000218...`, which is just over the cutoff, so legitimate matches silently failed. Fixed by comparing integer pence via `Math.round(n * 100)`.

After both fixes: 141 of 150 seeded matchable lines matched, with zero false matches. The 9 that fall through carry a vendor-name variant that deliberately fails the vendor-score threshold, and the classification stage handles them correctly downstream.

## Getting reliable structured output from the LLM

The classification step asks Claude for one bucket per line. The first implementation requested a JSON array as plain text and parsed it. Four separate things went wrong with that, each found by running real data rather than by code review:

1. A deprecated parameter. `temperature: 0` was rejected outright by the model and had to be removed.
2. A silently dropped field. The HTTP node replaces the item payload with the raw API response, so downstream code reading the original line data got `undefined` and produced zero output items with no error. Fixed by referencing the upstream node directly.
3. Response shape isn't fixed. The model sometimes prepends a reasoning block before the text block, so reading `content[0]` broke intermittently. Fixed by locating the text block by type.
4. The worst one only appeared at full scale. One entire 25-line batch came back wrapped in a Markdown code fence despite explicit instructions to return raw JSON. `JSON.parse` doesn't strip fences, so all 25 lines failed to parse and landed in "needs review", not because they were ambiguous but because of a formatting quirk. This never occurred in the 4-line test batches used during development. It took a real 25-line batch to trigger it.

The fix for the fourth bug was not to strip fences. It was to stop parsing text entirely. The classifier was reworked to use the API's forced tool-use: a tool with a strict input schema, forced via `tool_choice`, so the response arrives as parsed JSON and there is no free text to malform. That closes the whole class of formatting failures rather than patching one instance of it. A fence-stripping text fallback and an explicit stop-reason check were kept as a safety net.

## Making the AI trustworthy: the evidence check

A confidence score from a language model is not evidence. So every classification passes through a deterministic verification stage before it counts: is there a supporting accrual in the ledger for the claimed bucket, within amount and date tolerance? If yes, the line is verified. If the model and the ledger disagree, the line goes to a human. Nothing gets exported on the model's word alone.

This stage had its own tuning bug. The unresolvable-override path, where the evidence check overrules a model's "unresolvable" verdict because it found a plausible accrual, initially searched every bucket within a wide window. Against a full ledger it almost always found something, so genuinely unresolvable lines kept getting bumped to "needs review" even when the model had called them correctly. The fix was to require a vendor match on that override path specifically. The genuinely unresolvable lines carry counterparty names that match nothing in the ledger, so they now confirm as unresolvable, while the normal bucket-verification path was left untouched so it wouldn't break the intended vendor-variant fall-throughs. After the change, all 25 seeded unresolvable lines were correctly confirmed.

## Counting tokens honestly

The API reports token usage per call, but the workflow attaches that usage to every line in the call's batch. Summing naively across lines would multiply the real figure by the batch size. Each line is therefore tagged with the API response ID, and the scoring script deduplicates by that ID before summing. Any token or cost figure quoted from this project is the deduplicated one.

## Operational safety during development

The classification branch carried a hard cap limiting it to a handful of lines throughout development, so a full paid run could not be triggered by accident. The cap was removed and the batch size raised to production scale only for the final runs. The API call has retry with backoff, and a batch that still fails lands in "needs review" rather than sinking the whole execution.

## How this was built

The build itself was agentic. Claude Code drove a locally hosted n8n instance (Docker, exposed through a tunnel) via n8n's MCP server, creating and updating the workflow programmatically rather than click-by-click on the canvas. Direction, scope, and the quality bar sat with a human: what to build, what to cut, when a number was trustworthy enough to publish, when a run was allowed to spend real API money. The agent did the construction, testing, and debugging inside those constraints. Every bug in this document was found by executing real runs and inspecting the output, not by assuming the code was right.

It also didn't start from a blank page. The build ran on internal conventions that predate this project: a standing conventions file covering how workflows are structured, named, and exported, plus reusable build skills for n8n work. Where this build exposed gaps in those conventions, they were updated as part of the work, which is the point of keeping them.

A running build log was kept throughout, as standard protocol for our builds: every decision, bug, and dead end recorded as it happened. That log stays internal because it contains business context that doesn't belong in a public repo. This document is distilled from it.

## What would change for a real deployment

Two parts of this repo are testing scaffolding. The answer key, and the grading it enables, exist only because the data is synthetic; real data has no ground truth to score against. The Python script that does the grading also builds the Excel report, and in production that report step would move inside the workflow itself, with the grading half gone.

Beyond that, a real deployment needs: a live trigger instead of a manual one, the accruals pulled from the client's accounting system instead of a static file, buckets mapped to the client's actual accrual structure, and a proper vendor alias table instead of heuristic name matching. The pipeline and its control logic carry over as-is. The edges get wired into real systems.
