---
name: inframeld-application-contracts
description: Explains and reviews Inframeld application boundaries, shared HTTP/MCP/CLI behavior, transactions, jobs and safe retries. Use for orchestration and transport contracts. Backend declarations belong to Python Standards, and authored Rust conventions belong to Rust Standards.
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
- Native FastAPI/Pydantic OpenAPI drives generated clients. V1 delivers Rust CLI and the small Ory UI. CLI UX follows [clig.dev alignment and owned exceptions](references/cli-output-and-automation.md#follow-cligdev-and-record-product-exceptions). MCP retains its two accepted tools in the API process.
- All remote model calls use ModelGateway. Keep current connection access, credential rotation, spending and diagnostics under their owners.
- Do not introduce a generic executor, workflow engine, marker framework or architecture-enforcement tests.

## Explain or review

Trace validated input, verified identity, owning use case, transaction/external work and typed outcome. Then check response loss, repetition and changed state. Compare transports by scope, fixed inputs, receipts and outcomes. Inspect source before claiming implementation.

Code suggestions/reviews require Coding Standards and the affected language guidance. Backend services require Python Standards' [service example](../inframeld-python-standards/references/services-and-use-cases.md), aggregates/repositories its [load/action/save example](../inframeld-python-standards/references/aggregates-and-repositories.md). Use the domain architecture/workflow for domain components, or the relevant shared architecture below. Behavior tracing alone adds no Coding Standards prerequisite.

The [matching qualified CLI/runtime release policy](references/decision-cli-server-compatibility.md) is accepted through ADR-0095. Offline metadata does not verify a remote server. Release-pair qualification and remote enforcement remain delivery work.

## Accepted decision references

These contracts were approved on 2026-10-29. Apply them without reopening their policy. Implementation and qualification remain separate.

- [PD-CONTRACTS-05](references/decision-queue-saturation-and-cleanup.md): When selecting worker claim/scheduling behavior or making claims about recovery/cleanup progress under saturation.

- [PD-CONTRACTS-01](references/decision-gateway-enforcement.md): Before implementing model adapters/metadata/probe dispatch or selecting the actual transport/egress mechanism.
- [PD-CONTRACTS-02](references/decision-spending-coordination.md): Before implementing budget mutation, reservation, settlement, usage normalization or unknown-charge recovery.

## Pending decisions for affected work

Load only matching triggers. Discuss and obtain approval before code depends on an unresolved choice, following [decision finalization](../../../docs/development/guides/architecture-decisions.md). Unrelated decisions do not block work. Qualification gaps gate claims, not evidence-gathering tests.

- [PD-CONTRACTS-04](references/decision-import-review-and-recovery.md): Before implementing import planning/equivalence, admission ordering, child operations or interrupted-import recovery.

## Read as needed

Choose the row matching the task. Workflow, contract and architecture views are separate reading units. Do not load this whole table.

| Task | Direct reference |
| --- | --- |
| Artifact storage | [Publish immutable artifacts through the storage boundary](references/artifact-storage.md) |
| Shared CLI presentation components | [Share CLI presentation mechanics](references/cli-presentation-components.md), when designing presenters or shared output. |
| Rust CLI structure and lifecycle | [Typed command results and module boundaries](../inframeld-rust-standards/references/cli-structure.md), when designing the Rust adapter. |
| Cli change review | [Present an explicit before-and-after review](references/cli-change-review.md) |
| Cli context portability and recovery | [CLI context, portability and recovery](references/cli-context-portability-and-recovery.md) |
| Cli local runtime | [Manage the local runtime and its HTTP boundary](references/cli-local-runtime.md) |
| Cli output and automation | [CLI outcomes, automation and change presentation](references/cli-output-and-automation.md) |
| Cli result contracts | [Distinguish CLI command and background outcomes](references/cli-result-contracts.md) |
| Cli targets and accounts | [Select a CLI target, account and project](references/cli-targets-and-accounts.md) |
| Ownership, dependency direction or service boundaries | [Application boundaries and services](references/components-and-services.md) |
| Transfer concepts and operation boundaries | [Move definitions without copying an installation](references/configuration-export-and-import.md) |
| Configuration export | [Export one coherent configuration](references/configuration-export.md) |
| Configuration import recovery | [Continue a partial import without replacing its meaning](references/configuration-import-recovery.md) |
| Configuration import review | [Review destination-aware configuration changes](references/configuration-import-review.md) |
| Http error adapters | [Translate and report failures at HTTP boundaries](references/http-error-adapters.md) |
| Http errors | [Translate failures into safe HTTP problems](references/http-errors.md) |
| Http mcp and generated clients | [Share behavior across HTTP, MCP and generated clients](references/http-mcp-and-generated-clients.md) |
| Shared SDK generation policy or cross-language endpoint qualification | [SDKs skill](../inframeld-sdks/SKILL.md) |
| Language-specific SDK consumption or maintenance | [Rust](../inframeld-rust-sdk/SKILL.md), [TypeScript](../inframeld-typescript-sdk/SKILL.md) or [Python](../inframeld-python-sdk/SKILL.md), independently |
| Http problem contract | [Read the delivered HTTP problem contract](references/http-problem-contract.md) |
| Idempotency and replay | [Recognize a request and recover its original outcome](references/idempotency-and-replay.md) |
| Jobs and recovery | [Continue background work without repeating uncertain effects](references/jobs-and-recovery.md) |
| Original-request lookup and logical job/deletion outcomes | [Find original work and read its permitted outcome](references/operation-recovery-contracts.md), before designing or explaining lookup, inspection, cancellation or continuation interfaces. |
| Mcp transport | [Expose ordinary queries through the MCP adapter](references/mcp-transport.md) |
| Model connection changes | [Change shared current model connectivity](references/model-connection-changes.md) |
| Model dispatch and destinations | [Dispatch through the enforced model boundary](references/model-dispatch-and-destinations.md) |
| Shared gateway architecture | [One outbound model boundary](references/model-gateway-and-connections.md) |
| Model metadata and validation | [Separate model suggestions, saved settings and evidence](references/model-metadata-and-validation.md) |
| Model validation | [Validate real model use without making probes mandatory](references/model-validation.md) |
| Pagination | [Read one bounded authorized page](references/pagination.md) |
| Safe diagnostics | [Report failures without exposing protected values](references/safe-diagnostics.md) |
| Spending and accounting | [Reserve and account for model spending](references/spending-and-accounting.md) |
| Shared write/job architecture | [Transactions, durable jobs and safe retries](references/transactions-jobs-and-idempotency.md) |

## Source ownership

Focused references own accepted behavior and logical design. Code, generated OpenAPI and migrations own implemented representations. Read exact definitions when fields matter, ADRs for rationale or conflicts, and matching pending decisions before dependent design. Human guides own development procedures.
