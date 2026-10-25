---
name: inframeld-application-contracts
description: Explains and reviews Inframeld application boundaries, shared HTTP/MCP/CLI behavior, transactions, jobs and safe retries. Use for orchestration and transport contracts. Backend Python conventions belong to Coding Standards.
---

# Inframeld Application Contracts

Help a developer put one product behavior in its owning application workflow and expose it consistently. HTTP, MCP, CLI, future Studio and workers must not become independent implementations of permissions, retries or domain rules.

## Working model

Alice grants Bob permission and loses the response. A static HTTP mapper builds the Command. The application service opens a transaction, authorizes current scope, recognizes the operation identity, invokes membership behavior and saves audit/completion with the grant. Repeating the same request can recover its outcome, but still checks current authority first.

A transaction saves a group of database changes together or rolls them back together. Here the grant, audit and completed outcome must agree. A durable background job records work that can continue after the original request ends.

A command asks for a change. A query asks for a read. Keeping those responsibilities separate is called CQRS. A data transfer object (DTO) carries a result, projection or operation context. A Python protocol describes a capability the workflow needs without importing its database or vendor implementation. These distinctions support Clean Architecture without a command bus or generic repository.

The domain owns business decisions. Application services coordinate them. Adapters translate framework/provider/persistence boundaries. Bootstrap assembles and closes concrete resources. Read projections may join owners without acquiring another owner's write authority.

## Essential rules

- Keep each operation with its domain owner. Entry points share application behavior rather than becoming additional writers or permission engines.
- Keep HTTP, ORM and vendor SDK types outside application/domain contracts. Use application-owned typed values and secret-safe representations.
- Complete write services own transactions through direct injected capabilities. Authenticate first, authorize before reservation/replay, check returned scope and commit required audit with the change.
- Keep provider waits outside SQL transactions. Lower-level admission helpers retain caller-owned transaction contracts unless deliberately migrated.
- Preserve original operation meaning, identity and target on retry. Completed outcomes do not grant authority. A lost paid response does not authorize another dispatch.
- Native FastAPI/Pydantic OpenAPI drives generated clients. V1 delivers Rust CLI and the small Ory UI. MCP retains its two accepted tools in the API process.
- All remote model calls use ModelGateway. Keep current connection access, credential rotation, spending and diagnostics under their owners.
- Do not introduce a generic executor, workflow engine, marker framework or architecture-enforcement tests.

## Explain or review

Tracing existing request behavior, including inspecting its source, does not by itself require Coding Standards. Add that skill when proposing code or reviewing component structure, declarations or convention conformance.

1. Trace validated input, verified identity, owning use case, transaction/external work and typed outcome.
2. Explain a normal request before its lost-response retry, concurrent repeat or changed command.
3. Compare HTTP/MCP behavior by scope, selected input/version, receipt identity and outcome.
4. Before suggesting or reviewing any repository code, read [Coding Standards](../inframeld-coding-standards/SKILL.md), then applicable language guidance and the owning domain's rules. For backend services, read its [worked service example](../inframeld-coding-standards/references/services-and-use-cases.md). For aggregates or repositories, also read its [load, business action and save example](../inframeld-coding-standards/references/aggregates-and-repositories.md). Preserve runtime validation and protocol contracts.
5. Inspect source before claiming implementation. Separate source compatibility, recorded verification and unfinished delivery. Loading this skill grants no edits, SDK extraction, deployment or external mutations.

For domain-specific component design or structural code review, read that domain's architecture reference and relevant workflow. The [shared component view](references/components-and-services.md), [transaction/job view](references/transactions-jobs-and-idempotency.md) and [gateway view](references/model-gateway-and-connections.md) cover shared support. They create no additional business domain. A proposal in an owning guide remains pending until explicitly accepted.

## Read as needed

- For ownership, dependency direction, services or provider/session boundaries, read [Application boundaries and services](references/components-and-services.md).
- For writes, reservations, jobs, replay or uncertainty, read [Transactions, jobs and idempotency](references/transactions-jobs-and-idempotency.md).
- For native contracts, adapters, errors, pagination or client delivery, read [HTTP, MCP and generated clients](references/http-mcp-and-generated-clients.md).
- For target selection, imports, dry-runs, progress or recovery, read [CLI context, portability and recovery](references/cli-context-portability-and-recovery.md).
- For shared outbound execution and connection effects, read [ModelGateway and connections](references/model-gateway-and-connections.md).

The [application structure guide](../../../docs/development/application-structure.md) owns responsibilities. [API contracts](../../../docs/development/api-contracts.md) and [jobs](../../../docs/development/jobs-and-idempotency.md) own their behaviors. Access retains authentication/authorization policy ownership.
