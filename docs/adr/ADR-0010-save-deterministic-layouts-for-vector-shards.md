# ADR-0010: Save deterministic layouts for vector shards

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

A physical vector index may use several Chroma collections. Placement must remain explainable for retained generations rather than depend on an unrecorded current setting.

## Considered Options

- Saved layout and deterministic record placement within the single-host index.
- Implicit mutable placement or automatic distributed re-sharding in v1.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Record the scoped index’s layout and physical shard references and use the documented deterministic placement rule. Treat shards as partitions within the same server, not replicas or independent capacity. Retained bindings refer to their saved layout. Automatic re-sharding, multiple writer hosts, and distributed operation remain deferred.

**Example.** A record assigned to S0 is not automatically backed up by S1. Losing their shared host affects both shards.

## Consequences

- The application can locate and verify records according to the layout that produced their bindings.
- Fan-out, shared host resources, and migration costs remain real. Multiple collections provide neither high availability nor a measured capacity guarantee.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current indexing](../development/indexing.md).
- [Current data model](../development/data-model.md).
- [Current deployment](../development/deployment.md).
- Related decisions: [ADR-0009](ADR-0009-keep-application-authority-in-postgresql-and-derived-vectors-in-chroma.md), [ADR-0011](ADR-0011-retry-frozen-vector-identities-and-payloads.md).
