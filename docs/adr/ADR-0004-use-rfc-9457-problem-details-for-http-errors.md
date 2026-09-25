# ADR-0004: Use RFC 9457 Problem Details for HTTP errors

Status: Accepted

**Date:** 2026-09-17

## Context and Problem Statement

Clients need predictable failures without learning internal Python exception types or receiving sensitive diagnostic details.

## Considered Options

- RFC 9457 Problem Details with explicit application-to-HTTP mappings.
- Ad hoc error response shapes or direct serialization of arbitrary exceptions.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Use application/problem+json with the established Problem Details fields and bounded application extensions. Keep domain/application exceptions transport-independent. Only explicitly mapped failures receive public application problems; sanitize diagnostics and keep request correlation. The shared foundation is implemented as recorded in the existing maintainer reference.

**Example.** An inaccessible resource can receive the established safe not-found problem without exposing internal exception text or private resource details.

## Consequences

- Clients receive a consistent error contract while application rules remain independent of HTTP.
- Safe mappings, validation bounds, traceback handling, cancellation, and diagnostic behavior must be maintained. An unknown exception message is not safe merely because it is a string.

## Links

- [Current error handling](../development/error-handling.md).
- [Current error handling reference](../development/error-handling-reference.md).
- [Current api contracts](../development/api-contracts.md).
- Related decisions: [ADR-0003](ADR-0003-generate-the-authoritative-openapi-contract-from-backend-code.md), [ADR-0005](ADR-0005-use-bounded-cursor-pagination-for-lists.md), [ADR-0006](ADR-0006-use-official-generated-clients-for-application-api-access.md), [ADR-0007](ADR-0007-keep-api-documentation-public-and-product-operations-protected.md).
