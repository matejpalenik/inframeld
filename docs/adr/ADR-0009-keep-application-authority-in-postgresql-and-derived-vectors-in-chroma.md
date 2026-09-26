# ADR-0009: Keep application authority in PostgreSQL and derived vectors in Chroma

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

Several collection revisions can reuse unchanged vectors while requiring exact membership and current permissions. Putting mutable membership lists on every vector would require changing shared historical records.

## Considered Options

- PostgreSQL-owned membership with immutable numerical generations in Chroma.
- Mutable revision-membership arrays on vectors.
- A complete physical vector snapshot for every revision.
- Base-plus-delta or validity-range machinery.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Keep application identities, exact collection membership, current policy, and generation references in PostgreSQL. Store immutable derived numerical records in Chroma. Build each search filter on the server from exact membership and current access. Sharing unchanged generations does not make the stores one transaction.

**Example.** R2 can reuse GA and reference new GB2 while R1 still references GB1. The query filter selects the generations belonging to the chosen revision and permitted to the caller.

## Consequences

- Unchanged vectors can be reused without rewriting their revision membership, and the application remains the authority for permitted search scope.
- Complete membership assembly, verification, filtered search, and cleanup have real costs. The selected design requires qualification; source workload calculations are not measured capacity.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current indexing](../development/indexing.md).
- [Current data model](../development/data-model.md).
- Related decisions: [ADR-0010](ADR-0010-save-deterministic-layouts-for-vector-shards.md), [ADR-0011](ADR-0011-retry-frozen-vector-identities-and-payloads.md).
