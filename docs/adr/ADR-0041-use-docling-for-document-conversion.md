# ADR-0041: Use Docling for document conversion

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

The application needs a built-in way to convert supported documents into artifacts and chunks while retaining source relationships and a controlled processing boundary.

## Considered Options

- Docling behind an application-owned processing adapter.
- Let the converter define application identities or run as unrestricted application code.
- Build a general plugin platform before the initial processing path is qualified.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Use Docling for the selected built-in conversion path. Keep orchestration in the worker and conversion in the restricted attempt boundary. Produce application-owned artifacts and chunks under immutable processing profiles. Pin the required components and assets, validate output, and preserve internal extension contracts without adding an unused plugin platform.

**Example.** A converted section becomes a chunk with its source relationship only after the application validates the output. A parser-created identifier does not become a trusted document identity automatically.

## Consequences

- A concrete conversion component can be integrated without making its SDK or output format the application’s domain model.
- Supported inputs, assets, licenses, resource limits, output validation, and the pinned deployed implementation require qualification. A library selection does not establish isolation or production support.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current ingestion security](../development/ingestion-security.md).
- [Current data model](../development/data-model.md).
- Related decisions: [ADR-0042](ADR-0042-rerank-selected-evidence-through-a-local-cross-encoder-boundary.md).
