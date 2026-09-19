---
name: inframeld-application-contracts
description: Explain or review Inframeld application boundaries, HTTP and MCP contract parity, generated SDK/Studio integration, durable jobs and idempotency. Use when transport or orchestration changes could duplicate domain behavior or create unsafe retries; domain lifecycle details stay with their owner.
---

# Inframeld Application Contracts

Keep one application behavior behind HTTP, Studio, worker and MCP entry points.
This skill covers concrete cross-cutting mistakes: vendor types leaking inward,
transport-owned business state, lost-response retries, implicit privilege and
divergent generated clients. It is not another domain or a universal review gate.

## Scope and authority

Default to read-only assistance. Loading this skill grants no code edit, SDK
extraction, deployment or external mutation authority. Paths are repository-root
relative; inspect actual code only within the task scope. Read the guide's code,
client-surface and jobs sections, plus the owning contract for the task.

- `docs/ARCHITECTURE.md` is the product explanation.
- `docs/adr/ADR-0001-modular-application-structure.md` owns DDD/Clean Architecture
  and lightweight CQRS; `docs/adr/ADR-0002-product-owned-openapi-contract.md`
  owns the code-first public contract and generated TypeScript requirement.
- `docs/adr/ADR-0008-durable-jobs-idempotency-and-recovery.md` owns admission,
  attempts, fingerprints, safe replay and uncertainty.
- `docs/adr/ADR-0019-first-party-mcp-adapter.md` owns the accepted MCP surface.
- Read ADR-0018 for feedback, ADR-0020 for default-route orchestration, and
  ADR-0021 for credential mutations when those operations are being exposed.
- `docs/reviews/sdk-kit-feasibility.md` is external SDK evidence/status, not an
  instruction to extract it. For a requested runtime change only, consult
  ADR-0012/0013/0014; retain their existing baseline without expanding it.

## Owners, contracts and dependencies

Knowledge owns sources/memberships; Indexing owns verified search data;
Pipelines owns immutable RAG/query/receipt/feedback behavior; Evaluation owns
offline evidence; Releases owns pointers; Access owns authorization. Entry
points call their public application use cases. Read projections may join
owners; they do not become additional writers or an evidence microservice.

Jobs, idempotency reservations, operation status and audit are supporting
application records. They are not a seventh business bounded context, generic
saga system or event source. Domain objects enforce meaningful invariants;
immutable values and direct scoped read DTOs avoid unnecessary hydration.

## Contract rules

1. FastAPI/Pydantic is the OpenAPI authoring authority. Emit native OpenAPI 3.1.x
   following the selected version, commit generated output and check drift.
   Do not hand-edit it, relabel 3.1 as 3.0.3 or let SDK limitations redefine
   server semantics. Keep stable operation IDs, bounded pagination, explicit
   errors, async jobs and first-answer/replay variants.
2. SDK Kit is outside this repository. Its extraction/suitability blocks Studio
   development, not backend work. Python, Java, TypeScript and Rust are intended
   targets, not qualified deliverables. Studio's primary Inframeld client is the
   officially generated TypeScript SDK; do not bypass this with a handwritten
   client. Backend work can validate its contract without starting SDK Kit.
3. Browser SDK calls use the user's session/CSRF protections, never provider,
   integration or infrastructure secrets. Server-side Studio preserves the
   current user's context, without a global admin key or cross-user client cache.
   Kratos-owned account flows and framework rendering are justified separate
   contracts, not a second handwritten Inframeld business client.
4. Accepted MCP exposes only `query_deployment` and `get_answer_receipt`, mounted
   with the official Python SDK inside the API process. Reuse application
   authorization, filters, routing, ModelGateway and receipt outcomes. No
   independent RAG implementation, broad admin tool catalogue or new service.
5. Supported MCP clients are trusted header-capable clients preserving business
   idempotency keys. This is not universal OAuth discovery/sign-in compatibility.
   Authenticate every mounted request; ASGI mounting does not inherit protection
   automatically. Tool arguments cannot carry credentials or establish a subject.
   MCP request IDs are not business keys; exact SDK/protocol behavior needs tests.
6. Admit a command/job/idempotency reservation atomically in a short SQL
   transaction. Do external work outside it. Persist progress/final publication
   only for the current fenced attempt; a SQL lease never cancels a remote call.
7. Safe retries keep identity, payload and key. An asynchronous retry returns the
   original 202 job. Synchronous in-progress, completed safe replay and uncertain
   external outcomes are distinct. Ambiguous paid model work is not repeated
   automatically. Exact frozen vector insertion has a separate proven replay
   protocol in ADR-0005; do not generalize either rule to every operation.
8. Authenticate/authorize on replay. Same key/different content conflicts;
   expected revisions separately protect competing commands. Secret-bearing
   requests use keyed fingerprints; saved plaintext never enters replay caches.
   An answer replay returns receipt-only status; a generated integration secret
   is shown once. Clients must surface these outcomes honestly.
9. Defaults reuse ordinary application commands. ADR-0020 accepts automatic
   default updates and reversible per-deployment publication modes. New
   deployments default manual with an explicit automatic creation choice.
   Automatic operations call normal Build then separate conditional publication;
   Indexing never moves traffic. Mode switches use revisions/idempotency;
   enabling automatic admits fresh inputs, never revives an old job. Expose mode,
   current and pending update status through the same HTTP/SDK application API.
   MCP stays query/receipt only. All share the default resolver; its selector
   shape remains an implementation choice, not a parallel quickstart engine.

For the recommended default alias, find the original logical-route idempotency
record before resolving a fresh deployment target. A retry after promotion or
alias rebinding reads the original operation/receipt; it must not become another
paid query merely because the target changed. Read ADR-0020 for selector and
publication-mode concurrency details. Exact schemas and SDK behavior still
require qualification.

## Review method and useful tasks

Trace one request: validated transport DTO → verified context → owning use case →
short transaction/external boundary → safe result. Ask which layer owns each
decision. For a retry, compare lost response, concurrent same key and genuinely
different command. For HTTP/MCP parity, compare scope, selected version, receipt
identity and typed outcome rather than only schema names.

Use behavioral contract fixtures for native schema unions/nullability, bounded
uploads/cursors, errors, jobs, secret-safe responses and query replay. Proposed
tests are not executed evidence. Do not add a bus, workflow engine, exporter,
API gateway product or SDK-platform implementation to satisfy this skill.
