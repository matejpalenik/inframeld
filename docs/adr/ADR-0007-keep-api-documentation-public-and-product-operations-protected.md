# ADR-0007: Keep API documentation public and product operations protected

Status: Accepted

**Date:** 2026-09-17

## Context and Problem Statement

Developers need to inspect the API contract before integrating. Publishing documentation must not expose tenant data or make product operations anonymous.

## Considered Options

- Unauthenticated documentation and health endpoints, with authenticated and authorized product operations.
- Expose product operations or private operational details together with public documentation.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Keep the documented OpenAPI, Swagger UI, ReDoc, and health endpoints unauthenticated within their safe information boundary. Require authentication and authorization for product operations under /v1. Public documentation contains no organization data, source content, credentials, or sensitive internal operational detail.

**Example.** Reading the schema describes a deployment-query operation. Executing that operation still checks the caller and its current grants.

## Consequences

- Integrators can discover the contract without receiving access to protected application resources.
- Documentation examples, health output, and interactive calls must preserve the boundary. Public documentation does not grant the credentials required by Try it out.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current api contracts](../development/api-contracts.md).
- [Current access control](../development/access-control.md).
- Related decisions: [ADR-0003](ADR-0003-generate-the-authoritative-openapi-contract-from-backend-code.md), [ADR-0004](ADR-0004-use-rfc-9457-problem-details-for-http-errors.md), [ADR-0005](ADR-0005-use-bounded-cursor-pagination-for-lists.md), [ADR-0006](ADR-0006-use-official-generated-clients-for-application-api-access.md).
