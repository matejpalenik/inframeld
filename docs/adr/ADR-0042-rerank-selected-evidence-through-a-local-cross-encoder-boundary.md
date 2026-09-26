# ADR-0042: Rerank selected evidence through a local cross-encoder boundary

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

Similarity search produces candidate evidence. A reranker can improve ordering, but it must not independently retrieve hidden documents or create a second uncontrolled model path.

## Considered Options

- A local cross-encoder adapter operating only on application-supplied candidates.
- Let the reranker retrieve its own corpus or supply independent source identities.
- Require reranking for the first-answer path.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Use the selected local cross-encoder reranking approach behind an application-owned boundary. Supply only the already selected candidates and preserve their source identities. Bound inference work and recheck current access at the documented boundaries. The initial onboarding path may use its accepted preset without a reranker.

**Example.** If candidates A and B were supplied, a high reranker score cannot introduce private document C. The result still refers to the original permitted candidates.

## Consequences

- Reranking can refine permitted evidence without taking over retrieval scope or identity.
- The pinned model, assets, resource limits, result handling, and failure behavior require qualification. A selected reranker failure must not silently change the configured serving behavior.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current ingestion security](../development/ingestion-security.md).
- [Current pipelines and releases](../development/pipelines-and-releases.md).
- [Current data model](../development/data-model.md).
- Related decisions: [ADR-0041](ADR-0041-use-docling-for-document-conversion.md).
