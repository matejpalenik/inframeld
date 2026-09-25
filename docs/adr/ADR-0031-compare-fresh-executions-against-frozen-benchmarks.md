# ADR-0031: Compare fresh executions against frozen benchmarks

Status: Accepted

**Date:** 2026-09-17

## Context and Problem Statement

A comparison only means something when its test questions, evaluator, selected versions, and access conditions are known. Editing a case later must not rewrite an earlier result.

## Considered Options

- Freeze comparison inputs and execute both ready versions freshly through the ordinary query path.
- Compare results with unrecorded or changing benchmark/evaluator inputs.
- Treat old observations as directly comparable despite changed conditions.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

An explicit Compare operation freezes the selected baseline and candidate, benchmark, evaluator, and effective access scope, then runs both ready versions through normal application behavior. Preserve case/version history and report paired coverage, failures, skipped results, and metric denominators. The comparison does not move serving pointers or pause automatic publication.

**Example.** If the candidate fails a case, keep that failure visible. Dropping it from the denominator would make the candidate appear better without comparable evidence.

## Consequences

- Engineers can examine a like-for-like result and understand the conditions that produced it.
- Both pipeline runs and judge work have costs. Changed cases, evidence, or access can invalidate a comparison claim; model aliases do not prove repeatable remote behavior.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current evaluation](../development/evaluation.md).
- [Current data model](../development/data-model.md).
- Related decisions: [ADR-0030](ADR-0030-use-openevals-for-groundedness-evaluation.md).
