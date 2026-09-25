# ADR-0039: Block access before resumable physical deletion

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

Data may be referenced by current and historical pipeline versions, evaluation evidence, receipts, and backups. Deleting one object cannot honestly promise that every dependent physical copy disappeared immediately.

## Considered Options

- A scoped deletion marker followed by reference-aware resumable cleanup.
- Treat access revocation as proof of physical erasure.
- Delete shared or unowned data without checking its live relationships.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Apply an authoritative deletion marker first to block new use and late publication. Then remove known-owned data through bounded, resumable cleanup that respects the accepted distinction between routine expiry and explicit erasure. Apply current access to historical reads, and reconcile deletion restrictions before restoring service from backups.

**Example.** Erasing document B differs from leaving B out of a new collection revision. Erasure may make an older pipeline that needs B unavailable.

## Consequences

- The application can stop exposing deleted information while completing cleanup safely and visibly.
- Explicit erasure can invalidate historical releases or evidence. External providers and retained backups have separately disclosed limits; already dispatched requests cannot be recalled by a database change.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current retention and deletion](../development/retention-and-deletion.md).
- [Current knowledge lifecycle](../development/knowledge-lifecycle.md).
