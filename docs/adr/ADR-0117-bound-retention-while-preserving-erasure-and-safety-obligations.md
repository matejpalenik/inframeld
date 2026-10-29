# ADR-0117: Bound retention while preserving erasure and safety obligations

**Status:** Accepted

**Date:** 2026-10-29

## Context and Problem Statement

Keeping everything forever eventually exhausts the host and makes erasure harder. Finite defaults make normal growth predictable, while safety obligations cannot be discarded just because a timer expired.

## Considered Options

- Use the focused bounded contract above. Selected.
- Expose independent unbounded family policies, increasing storage and erasure inconsistencies.

## Decision Outcome

Apply the [complete accepted PD-KNOWLEDGE-02 contract](../../.agents/skills/inframeld-knowledge/references/decision-retention-erasure-policy.md#approved-resolution). It owns the exact behavior, bounds, current-state checks and failure outcomes. Use one finite installation retention profile with owner-specific content rules. Select these default/operator-maximum periods: unreferenced source versions, collection revisions and derived artifacts 30/90 days; historical working configuration 90/365 days; completed execution-capture metadata 7/30 days; Evaluation run answers, judgments and supporting evidence 90/365 days; answer receipts, associated feedback and deletion-status projections 30/90 days; completed job/attempt history 30/90 days; protected workload traces 30/90 days; content-free operational logs 7/30 days; ordinary audit history 365/730 days. These are selected policy values, not regulatory advice or measured cleanup performance. Project workload-trace retention keeps its already accepted configurable 30-day default. A shorter setting needs a reviewed ordinary authorized policy update, not a hidden global reset.

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Consequences

Historical experiments may become unavailable. Live references and required safety evidence remain, so reaching storage limits stops new work rather than destroying needed records.

Alice's old evaluation evidence normally expires after 90 days. If Bob erases its source sooner, protected derived text becomes unavailable immediately. A still-unresolved cleanup record survives until its obligation and backup restrictions are safely satisfied.

Implementation, measured support and qualification remain separate. A chosen threshold is not a measured result. No application code, public endpoint or passing runtime evidence is delivered here.

## Links

- [Owning contract](../../.agents/skills/inframeld-knowledge/references/decision-retention-erasure-policy.md#approved-resolution)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
