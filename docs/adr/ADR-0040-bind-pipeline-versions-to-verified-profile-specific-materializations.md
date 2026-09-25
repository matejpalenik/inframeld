# ADR-0040: Bind pipeline versions to verified profile-specific materializations

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

The same admitted source can be processed and embedded under different configurations. A source upload or a matching semantic input key does not prove that all numerical records needed for serving exist.

## Considered Options

- Explicit immutable profiles, generations, verified materializations, and complete pipeline bindings.
- Couple admission permanently to one embedding profile.
- Treat a source upload, shard-wide count, or past ready label as proof of current usable data.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Keep source admission, processing, numerical generations, and materialization readiness distinct. Verify exact required records before publishing complete bindings for a ready pipeline version. Preserve separate historical readiness and current availability checks. Reuse compatible prepared results without treating a fresh numerical execution as the same physical output.

**Example.** Changing a prompt may reuse the same materialization. Changing embedding meaning requires the matching profile and prepared numerical records before the version can serve.

## Consequences

- The application can reuse existing work while retaining precise evidence that a selected version was prepared correctly.
- Snapshot assembly and verification can examine the complete selected corpus. Missing dependencies can make a previously ready version unavailable; no untested capacity guarantee follows from reuse.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current indexing](../development/indexing.md).
- [Current data model](../development/data-model.md).
- [Current pipelines and releases](../development/pipelines-and-releases.md).
