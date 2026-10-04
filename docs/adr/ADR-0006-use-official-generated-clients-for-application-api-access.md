# ADR-0006: Use official generated clients for application API access

Status: Accepted; external tooling prerequisite partially superseded by [ADR-0055](ADR-0055-deliver-cli-first-v1-through-openapi-generated-clients.md).

**Date:** 2026-09-17

## Context and Problem Statement

Studio and external integrations need to follow the same authoritative HTTP schema without maintaining competing handwritten transport models.

## Considered Options

- Official SDKs generated from the authoritative OpenAPI contract.
- Handwritten parallel Studio clients or client-owned request/response contracts.
- Weaken the backend schema to fit an unqualified generator.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

The original decision selected the official generated TypeScript client in Studio, thin transports and preservation of the acting user's identity. It treated an external generator project's suitability as a prerequisite for Studio, while backend development proceeded independently. ADR-0055 replaces that delivery dependency with generator-neutral OpenAPI clients and CLI-first v1; it preserves generated contracts, thin transports and runtime compatibility qualification. No custom generator development is implied.

**Example.** A server-rendered Studio request must preserve the user’s authority rather than use a global administrator credential to make the SDK call succeed.

## Consequences

- Clients derive request and response shapes from the public contract and reuse the application’s behavior.
- Generator suitability, output semantics, and client integration still need verification. Intended SDK target languages are not automatically qualified deliverables.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current api contracts](../development/api-contracts.md).
- Related decisions: [ADR-0003](ADR-0003-generate-the-authoritative-openapi-contract-from-backend-code.md), [ADR-0004](ADR-0004-use-rfc-9457-problem-details-for-http-errors.md), [ADR-0005](ADR-0005-use-bounded-cursor-pagination-for-lists.md), [ADR-0007](ADR-0007-keep-api-documentation-public-and-product-operations-protected.md).
