# ADR-0044: Provide MCP through a thin adapter in the existing API process

Status: Accepted

**Date:** 2026-09-19

## Context and Problem Statement

Customers want to query deployed knowledge through MCP without a second implementation of retrieval, permissions, retries, and result handling.

## Considered Options

- A first-party in-process adapter using the official SDK and shared application use cases.
- Expose every HTTP operation automatically as a tool.
- Create another retrieval service or proxy all tools through internal HTTP.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Mount the MCP adapter inside the existing API process and expose the selected query-deployment and get-answer-receipt tools. Reuse application behavior and verified caller context. Keep the transport contracts distinct while preserving authorization, serving selection, receipt, and business-retry semantics. The client-support decision is recorded separately.

**Example.** A tool request for an answer receipt passes the same current evidence-access checks as an HTTP request. Knowing a receipt ID is not permission to read it.

## Consequences

- MCP uses the same business rules and prepared knowledge as the ordinary API.
- Mounted authentication, parent lifespan, resource binding, errors, network restrictions, SDK integration, and interoperability need qualification. An available SDK is not proof that every client is supported.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current mcp](../development/mcp.md).
- [Current api contracts](../development/api-contracts.md).
- Related decisions: [ADR-0045](ADR-0045-support-preconfigured-mcp-clients-with-application-credentials.md).
