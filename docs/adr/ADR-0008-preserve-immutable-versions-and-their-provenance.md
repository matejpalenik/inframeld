# ADR-0008: Preserve immutable versions and their provenance

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

Engineers need to explain which documents, processing choices, numerical outputs, and pipeline settings produced a result. Following mutable latest values would change the meaning of saved releases and evaluations.

## Considered Options

- Give stable concepts identities and preserve immutable versions and explicit relationships.
- Treat the latest source or settings as the meaning of a saved version.
- Conflate a reusable input description with one actual numerical execution.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Keep logical identities separate from their immutable contents and actual processing outputs. A collection revision selects exact document versions; a pipeline version freezes complete configuration and prepared bindings. Preserve the relationships needed to explain serving and evaluation results. Current access and availability checks still apply to historical records.

**Example.** R1 contains A1 and B1. Replacing B creates B2 and R2. R1 still means A1 and B1, although deletion or revoked access may prevent using it now.

## Consequences

- A later edit does not silently rewrite what an earlier version or result meant.
- Provenance requires stored relationships and retention-aware reads. Recorded inputs do not promise byte-identical future model output or restore missing numerical data.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current data model](../development/data-model.md).
- [Current knowledge lifecycle](../development/knowledge-lifecycle.md).
- [Current pipelines and releases](../development/pipelines-and-releases.md).
