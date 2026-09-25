---
name: inframeld-application-contracts
description: Explain or review Inframeld application boundaries, HTTP and MCP contract parity, generated SDK/Studio integration, durable jobs and idempotency. Use when transport or orchestration changes could duplicate domain behavior or create unsafe retries; domain lifecycle details stay with their owner.
---

# Inframeld Application Contracts

Keep one application behavior behind HTTP, Studio, workers, and MCP. Review ownership, safe retries, generated contracts, and transport boundaries without creating another domain or a universal review gate.

## Scope and reading route

Default to read-only assistance. Loading this skill grants no code edits, SDK extraction, deployment, or external mutations. Paths are repository-relative. Read the relevant guide section and decision, cite it, and distinguish design from inspected implementation.

- [Application structure](../../../docs/development/application-structure.md) owns responsibilities and dependency rules; [ADR-0001](../../../docs/adr/ADR-0001-use-one-modular-backend-with-clear-domain-boundaries.md) and [ADR-0002](../../../docs/adr/ADR-0002-separate-commands-and-queries-without-a-command-bus-framework.md) explain the modular backend and command/query choices.
- [API contracts](../../../docs/development/api-contracts.md) owns public interfaces and clients; [ADR-0003](../../../docs/adr/ADR-0003-generate-the-authoritative-openapi-contract-from-backend-code.md) and [ADR-0006](../../../docs/adr/ADR-0006-use-official-generated-clients-for-application-api-access.md) explain contract generation and official clients.
- [Error handling](../../../docs/development/error-handling.md) and its [maintainer reference](../../../docs/development/error-handling-reference.md) own the implemented RFC 9457 foundation and evidence. [Pagination](../../../docs/development/pagination.md) owns the implemented shared models; each feature still validates cursor contents and scope.
- [Jobs and idempotency](../../../docs/development/jobs-and-idempotency.md) owns admission, attempts, replay, uncertainty, and revisions. [Supporting records](../../../docs/development/data-model.md#shared-supporting-records) owns their record definitions.
- [MCP](../../../docs/development/mcp.md) owns the accepted two-tool client and transport contract. Read [Onboarding](../../../docs/development/onboarding.md), [Feedback](../../../docs/development/answer-feedback.md), or [Model connections](../../../docs/development/model-connections.md) when exposing those operations.
- For Access contracts, read [the Access data model](../../../docs/development/data-model.md#access) and [write coordination](../../../docs/development/access-control.md#section-accepted-write-coordination-and-proposed-indexes). The Access skill supplies policy context; adapters must not invent permissions.
- [Maintainer checks](../../../docs/development/application-structure.md#maintainer-checks) summarize the behavioral review scenarios. The old SDK Kit report is [unavailable](../../../docs/development/documentation-maintenance.md#missing-sdk-kit-review); it does not establish interoperability.

- Follow [a command and query](../../../docs/development/application-structure.md#operation), then [request identity](../../../docs/development/jobs-and-idempotency.md#requests) and [lost-answer recovery](../../../docs/development/jobs-and-idempotency.md#answers). For MCP parity, read [its tool contract](../../../docs/development/mcp.md#tools).

## Essential boundaries

Knowledge owns sources; Indexing owns verified search data; Pipelines owns builds, query, receipts and feedback; Evaluation owns offline evidence; Releases owns serving pointers; Access owns authorization. Entry points call their public application use cases. Read projections may join owners without becoming additional writers. Jobs and audit are supporting records, not a seventh domain or event-sourcing framework.

Keep vendor SDK, HTTP, and ORM types outside application/domain contracts. Supply verified application-owned identity context. Shared authorization uses current grants and transactional audit. Group-manager appointment and recovery explicitly record ordinary membership too. Membership removal also removes management in the same transaction. Preserve the [required relationship](../../../docs/development/data-model.md#group-manager-membership-constraint) without treating manager status as a read bypass. Target-specific relational persistence does not imply multiple policy implementations. Grant, scope-revision, and account-status mutations participate in the accepted lock protocol.

FastAPI/Pydantic generates the native OpenAPI 3.1.x contract. Keep stable operation IDs, errors, bounded pagination, asynchronous outcomes, and first-answer/receipt-only variants. Do not hand-edit generated output or weaken server semantics for a generator. Shared pagination bounds `limit` to 1–100, default 25; feature-owned deterministic order includes a unique tie-breaker and current authorization on every page.

Studio uses the official generated TypeScript SDK. SDK Kit is external and blocks Studio suitability, not backend work. Intended Python, Java, TypeScript, and Rust targets are not qualified deliverables. Browser calls use the user’s session and CSRF protections; server rendering preserves that user’s context without a global admin key or cross-user cached client. Kratos account flows and framework rendering have their own justified contracts.

MCP exposes only `query_deployment` and `get_answer_receipt` inside the existing API process. Authenticate every mounted request, reuse application behavior, and preserve business idempotency keys. Mounting does not automatically inherit protection. Header-capable trusted clients are supported; universal OAuth discovery and verified per-user delegation are not implied. Tool arguments and MCP request IDs cannot establish credentials or business retry identity.

Admit work and its idempotency reservation atomically in a short transaction. Do external work outside it; only the current fenced attempt can publish. A SQL lease cannot cancel a remote request. Same key and meaning finds the original operation; different meaning conflicts. Authenticate and authorize replay. Keep secret-bearing fingerprints keyed, generated secrets one-time, and answer replay receipt-only. Ambiguous paid calls cannot be silently repeated; frozen vector payload retries have their separate bounded protocol.

Defaults reuse normal commands and one resolver. Automatic updates uses normal Build then separate conditional publication; Indexing never moves traffic. Revisions protect mode switches and competing commands. For a default alias retry, locate the original logical-route idempotency record before resolving a new target, so rebinding cannot create another paid query. Selector details remain implementation recommendations.

## Review method

Trace validated request → verified context → owning use case → transaction or external call → typed outcome. Compare a lost response, concurrent repeat, and different command. For HTTP/MCP parity compare scope, selected version, receipt identity, and outcome. Use behavior and contract checks when implementation is authorized; do not add structural tests, speculative frameworks, or start SDK Kit work by implication.
