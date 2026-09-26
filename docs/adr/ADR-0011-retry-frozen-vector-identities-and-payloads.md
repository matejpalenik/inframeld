# ADR-0011: Retry frozen vector identities and payloads

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

A vector insert can succeed remotely even when its response is lost. Retrying with new numerical output or overwriting a retained identity would make history unreliable.

## Considered Options

- Freeze exact bounded IDs and bytes, retry them, then verify actual records.
- Regenerate numerical output for the same physical identity.
- Restart healthy Chroma as the normal response to an uncertain candidate insert.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Use the single-writer protocol and persist the exact bounded vector payload before dispatch. Retry identical physical IDs and bytes within the documented bounds, verify the expected records, and publish readiness only under current SQL ownership. Keep exceptional cleanup and missing published data separate from ordinary insert retry.

**Example.** Retrying saved GB2 vector bytes is different from calling the model again to create another GB2. A fresh numerical execution needs a fresh identity.

## Consequences

- Lost insert responses can be handled without changing retained numerical meaning or interrupting healthy generations unnecessarily.
- SQL fencing does not cancel external writes. Corrupt saved payloads, unresolved deletion races, or lost published data can still require intervention. An uncertain embedding-model call is not covered by this vector-write retry rule.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current indexing](../development/indexing.md).
- [Current jobs and idempotency](../development/jobs-and-idempotency.md).
- Related decisions: [ADR-0009](ADR-0009-keep-application-authority-in-postgresql-and-derived-vectors-in-chroma.md), [ADR-0010](ADR-0010-save-deterministic-layouts-for-vector-shards.md).
