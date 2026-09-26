# ADR-0005: Use bounded cursor pagination for lists

Status: Accepted

**Date:** 2026-09-17

## Context and Problem Statement

Lists need bounded responses and repeatable ordering as data grows. A paging token must not become permission to read data outside the caller’s current scope.

## Considered Options

- Opaque cursors with bounded limits and deterministic ordering.
- Unbounded lists or cursors treated as trusted authorization.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Use an optional opaque cursor and a limit from 1 to 100, defaulting to 25. Return items and a nullable nextCursor. End each ordering with a unique tie-breaker, validate the cursor against the owning query, and reapply authorization on every page. The shared HTTP shape is implemented; each feature owns its scoped query.

**Example.** Losing a permission between page one and page two must affect page two, even if the cursor was issued while the permission existed.

## Consequences

- Responses remain bounded and clients can continue a list through one shared contract.
- Each feature must choose meaningful ordering, filters, cursor validation, and current visibility checks. The shared model does not implement its database query.

## Links

- [Current pagination](../development/pagination.md).
- [Current api contracts](../development/api-contracts.md).
- Related decisions: [ADR-0003](ADR-0003-generate-the-authoritative-openapi-contract-from-backend-code.md), [ADR-0004](ADR-0004-use-rfc-9457-problem-details-for-http-errors.md), [ADR-0006](ADR-0006-use-official-generated-clients-for-application-api-access.md), [ADR-0007](ADR-0007-keep-api-documentation-public-and-product-operations-protected.md).
