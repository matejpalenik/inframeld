# ADR-0003: Generate the authoritative OpenAPI contract from backend code

Status: Accepted

**Date:** 2026-09-17

## Context and Problem Statement

Studio and customer clients need one accurate description of request fields, responses, errors, and authentication. A separately handwritten contract can drift away from the running FastAPI application.

## Considered Options

- Generate the contract from FastAPI, Pydantic models, and application metadata.
- Maintain OpenAPI separately by hand.
- Let each client define its own transport models.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Generate the public versioned contract from backend code, using native OpenAPI 3.1.x emitted by the selected backend versions. Keep the generated artifact reviewable in Git and check for drift. Do not edit generated output by hand, relabel a 3.1 document as 3.0, or weaken the contract to accommodate a client generator.

**Example.** Adding a request field in the backend changes the generated schema. A client must be regenerated or updated through the approved SDK path rather than inventing a competing field shape.

## Consequences

- The contract used by clients comes from the application that handles their requests.
- Schema generation, stable operation identifiers, error declarations, and client compatibility need qualification. External SDK Kit limitations can block Studio integration; they do not justify blocking backend work or changing valid contract meaning.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current api contracts](../development/api-contracts.md).
- Related decisions: [ADR-0004](ADR-0004-use-rfc-9457-problem-details-for-http-errors.md), [ADR-0005](ADR-0005-use-bounded-cursor-pagination-for-lists.md), [ADR-0006](ADR-0006-use-official-generated-clients-for-application-api-access.md), [ADR-0007](ADR-0007-keep-api-documentation-public-and-product-operations-protected.md).
