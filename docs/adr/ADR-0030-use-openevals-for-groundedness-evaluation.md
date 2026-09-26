# ADR-0030: Use OpenEvals for groundedness evaluation

Status: Accepted

**Date:** 2026-09-17

## Context and Problem Statement

Engineers need a useful check of whether an answer is supported by the evidence actually supplied to generation. Building or operating a separate evaluation platform would expand the v1 scope.

## Considered Options

- OpenEvals groundedness through the application model boundary.
- Ragas claim-based faithfulness.
- DeepEval faithfulness.
- A custom native judge.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Use OpenEvals for the selected holistic groundedness check. Qualify configurable GPT-6 Luna as the baseline judge through ModelGateway, with the recorded rubric and strict result handling. Inframeld owns cases, snapshots, runs, comparisons, and history. No hosted evaluation-platform account is required.

**Example.** Judge the answer against the final evidence after reranking and truncation. A source retrieved earlier but absent from that final context cannot justify the answer in this check.

## Consequences

- The application can use a maintained evaluation component while keeping its own evidence, access, and model-call boundaries.
- Calibration and integration are still required. Groundedness is not truth, completeness, relevance, or a percentage of extracted claims. Invalid judge output is a failure, not an ordinary negative verdict; scores never authorize releases.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current evaluation](../development/evaluation.md).
- [Current model connections](../development/model-connections.md).
- [Current data model](../development/data-model.md).
- Related decisions: [ADR-0031](ADR-0031-compare-fresh-executions-against-frozen-benchmarks.md).
