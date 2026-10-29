# ADR-0107: Reference exact verified index materializations

**Status:** Accepted

**Date:** 2026-10-29. The developer explicitly approved all three document-batch, prepared-binding and source-coordinate proposals, including their detailed contracts, and requested repository and GitHub recording. Acceptance selects logical behavior, not implemented code or passing qualification.

## Context and Problem Statement

A query needs exact verified prepared data while another operation prepares a newer revision or retires old generations. A mutable name or ready flag cannot define those dependencies or protect their lifetime.

## Considered Options

- A scoped existing IndexMaterialization identity plus a complete bounded verified projection. Selected.
- Copy the complete immutable binding value between callers, requiring larger messages and careful size bounds.

## Decision Outcome

Use the existing scoped IndexMaterialization identity, explicit typed projections and immutable paged manifests. Identify exact corpus, profiles, generations, layout and complete verification evidence. Resolve and pin selected usable data through the shared retention gate. Missing or incompatible required data fails without substitution or partial search. Readiness does not replace current authority or health, and explicit erasure overrides ordinary pins.

The [approved PD-INDEXING-01 contract](../../.agents/skills/inframeld-indexing/references/decision-capability-binding-contracts.md#approved-resolution) owns the complete behavior, examples and required cases.

## Consequences

Scoped reads and explicit pin ownership add work but keep messages bounded and prevent ordinary retirement races. Stale bindings cannot silently resolve to newer numerical data. Exact current-health detection remains with PD-INDEXING-02 and numerical retention settings retain their owning decisions.

Backend implementation, public schemas and runtime qualification remain separate delivery work.

## Links

- [Stable decision reference](../../.agents/skills/inframeld-indexing/references/decision-capability-binding-contracts.md)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
