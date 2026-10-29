# ADR-0119: Bound frozen storage retries and prove exceptional erasure completion

**Status:** Accepted

**Date:** 2026-10-29

## Context and Problem Statement

A timed-out storage request may still finish later. Reusing already known bytes is different from buying another embedding, and deleting data is not complete while old writes could recreate it.

## Considered Options

- Use the focused bounded contract above. Selected.
- Use an engine-specific online completion guarantee once proven; absent that evidence it cannot certify erasure.

## Decision Outcome

Apply the [complete accepted PD-INDEXING-04 contract](../../.agents/skills/inframeld-indexing/references/decision-storage-retries-and-erasure.md#approved-resolution). It owns the exact behavior, bounds, current-state checks and failure outcomes. Keep immutable generation IDs, exact explicit record IDs and frozen canonical finite float32 payload bytes before vector dispatch. Retrying storage reuses those exact bytes and recorded placement. Verify actual numerical/content readback against the trusted frozen expectation and qualified engine representation. A conflicting existing ID/payload is an integrity failure, not permission to overwrite or regenerate. This does not authorize another possibly billed embedding call.

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Consequences

Exceptional cleanup may briefly stop affected stores. If the backend cannot prove completion, the honest outcome is pending physical cleanup, not a false erasure guarantee.

Alice deletes retired generation G1 after a retry succeeded. Bob's original delayed request could still arrive. G1 remains blocked immediately, but final erasure is reported only after the proven completion barrier excludes that old write.

Implementation, measured support and qualification remain separate. A chosen threshold is not a measured result. No application code, public endpoint or passing runtime evidence is delivered here.

## Links

- [Owning contract](../../.agents/skills/inframeld-indexing/references/decision-storage-retries-and-erasure.md#approved-resolution)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
