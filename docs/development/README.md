# Develop Inframeld

<a id="develop-inframeld"></a>

Start the backend, learn one workflow and follow its owner when you need details. The application is being built toward an accepted architecture. A documented feature is not automatically an implemented or qualified feature.

<a id="start-working"></a>

## Start working

| Your task | Start here |
| --- | --- |
| Run today’s backend | [Local setup](getting-started/local-setup.md) |
| Understand the product | [Architecture introduction](../ARCHITECTURE.md) and [first-answer journey](getting-started/first-answer.md) |
| Run one test or private integration stack | [Testing](guides/testing.md) |
| Investigate a failure safely | [Debugging](guides/debugging.md) |
| Add a backend behavior | [Worked contributor guide](guides/adding-a-backend-feature.md) |
| Find an HTTP field, logical record or database constraint | [Contracts and data](guides/contracts-and-data.md) |
| Consume or maintain the Rust SDK and generator patches | [Rust SDK skill](../../.agents/skills/inframeld-rust-sdk/SKILL.md) and [workspace runbook](../../packages/sdk-tools/README.md) |
| Extend shared SDK coverage or maintain generator inputs | [SDKs skill](../../.agents/skills/inframeld-sdks/SKILL.md) |
| Consume or maintain the TypeScript or Python SDK | [TypeScript](../../.agents/skills/inframeld-typescript-sdk/SKILL.md), [Python](../../.agents/skills/inframeld-python-sdk/SKILL.md) and [language runbook](../../packages/sdk-tools/README.md) |
| Understand SDK tooling or add endpoint coverage | [Architecture map](../../packages/sdk-tools/docs/architecture.md), [endpoint walkthrough](../../packages/sdk-tools/docs/adding-endpoint.md) and [generator walkthrough](../../packages/sdk-tools/docs/generators.md) |
| Choose test layers, isolation or interpret test evidence | [Testing skill](../../.agents/skills/inframeld-testing/SKILL.md) |
| Read historical Rust generator qualification | [Rust SDK comparison](reports/rust-sdk-generator-comparison.md) |
| Read historical TypeScript/Python generator qualification | [Language SDK comparison](reports/typescript-python-sdk-generator-comparison.md) and [runbook](../../packages/sdk-tools/README.md) |
| Operate, upgrade or restore an installation | [Runtime](operations/runtime-and-networking.md), [upgrades](operations/upgrades.md), [backup and restore](operations/backup-and-restore.md) |
| Understand a public HTTP problem | [Problem catalogue](error-handling.md) |
| Review code or decide commit/merge readiness | [Review skill](../../.agents/skills/inframeld-review/SKILL.md) and its [standard report](../../.agents/skills/inframeld-review/references/scoring-and-report.md) |
| Finish or document a change | [Definition of Done](definition-of-done.md) and [documentation maintenance](documentation-maintenance.md) |

<a id="find-the-detailed-owner"></a>

## Find the detailed owner

The skill references are written for people as well as coding agents. They own detailed accepted behavior and architecture. Read a focused workflow directly. You do not need to load every skill or the full glossary first.

- [Access](../../.agents/skills/inframeld-access-models/SKILL.md): identity, authentication, grants, recovery and credential protection.
- [Original-request lookup](guides/original-request-lookup.md): recover retained admission under current authority without repeating work.
- [Knowledge](../../.agents/skills/inframeld-knowledge/SKILL.md): documents, immutable versions, collections and source synchronization.
- [Indexing](../../.agents/skills/inframeld-indexing/SKILL.md): parsing, embeddings, verified search data and cleanup.
- [Pipelines](../../.agents/skills/inframeld-pipelines/SKILL.md): configuration, ordinary execution, receipts, feedback and tracing.
- [Evaluation](../../.agents/skills/inframeld-evaluation/SKILL.md): cases, frozen tests, fresh comparisons and protected evidence.
- [Releases](../../.agents/skills/inframeld-releases/SKILL.md): serving selection, Automatic/Manual transitions and rollback.
- [Application Contracts](../../.agents/skills/inframeld-application-contracts/SKILL.md): transactions, jobs, transports, CLI and ModelGateway.
- [Rust SDK](../../.agents/skills/inframeld-rust-sdk/SKILL.md): generated client consumption, qualification and pinned generator patches.
- [SDKs](../../.agents/skills/inframeld-sdks/SKILL.md): common generation policy, endpoint delivery and cross-language qualification. Language skills remain independently discoverable.
- [TypeScript SDK](../../.agents/skills/inframeld-typescript-sdk/SKILL.md): Hey API Fetch/Zod consumption, browser limits and packaging.
- [Python SDK](../../.agents/skills/inframeld-python-sdk/SKILL.md): OpenAPI Generator HTTPX/Pydantic consumption, lifecycle and packaging.
- [Testing](../../.agents/skills/inframeld-testing/SKILL.md): test layers, controlled dependencies, integration isolation and honest verification evidence.
- [Review](../../.agents/skills/inframeld-review/SKILL.md): structured code and architectural review, calibrated ratings and separate commit/merge readiness.
- [Coding Standards](../../.agents/skills/inframeld-coding-standards/SKILL.md): shared engineering, TDD/documentation and language routing.
- [Python Standards](../../.agents/skills/inframeld-python-standards/SKILL.md): backend component conventions and complete Python examples, with client/tooling exclusions.
- [Rust Standards](../../.agents/skills/inframeld-rust-standards/SKILL.md): authored Rust idioms, checks, [selected CLI libraries](../../.agents/skills/inframeld-rust-standards/references/cli-libraries.md) and the [accepted CLI structure and lifecycle](../../.agents/skills/inframeld-rust-standards/references/cli-structure.md).
- [Shared CLI presentation](../../.agents/skills/inframeld-application-contracts/references/cli-presentation-components.md): accepted component responsibilities consuming the output/result contracts, with runtime integration pending.
- [Architecture](../../.agents/skills/inframeld-architecture/SKILL.md): system context, runtime and cross-domain journeys.

<a id="authority-and-unresolved-choices"></a>

## Authority and unresolved choices

Code defines implemented types, generated OpenAPI defines the delivered HTTP representation and migrations define the database. [ADRs](../adr/README.md) record accepted choices and supersession. Logical design may be accepted while its implementation remains unfinished.

Pending decisions have stable `PD-*` identifiers and remain explicitly unresolved. Find the matching trigger through its owning skill. Follow [the just-in-time process](guides/architecture-decisions.md#just-in-time-architecture-decisions) before dependent design or code. An unrelated pending decision does not block ordinary work.

<a id="older-issue-links"></a>

## Older issue links

Historical GitHub issues may cite removed developer guides and anchors. Those issue bodies and comments have intentionally not been rewritten. Use the current owners above and the pending decision references for today’s guidance. Git preserves removed reports when provenance is needed.

## Focused procedures

- [Optional identity integration](guides/identity-integration.md)
- [Author skills and references](guides/skill-authoring.md)
- [Discuss architecture decisions](guides/architecture-decisions.md)
- [Back up](operations/backups.md), [restore](operations/restore.md) and [qualify recovery](operations/recovery-qualification.md)

For SDK response integrity, native typing and package-consumption evidence, see the [hardening report](reports/sdk-hardening-verification.md) and [SDK runbook](../../packages/sdk-tools/README.md).

The subsequent [response-fix verification and architectural review](reports/sdk-response-fixes-verification.md) covers typed failures, status/media variants and safe transport defaults under [ADR-0094](../adr/ADR-0094-select-sdk-response-variants-and-safe-transport-defaults.md).

- [Rust CLI foundation](../../apps/cli/README.md): commands, strict Rust checks, native archives and explicit installation/removal.

For public metadata configuration and stateless client validation, read [server discovery](guides/server-discovery.md).
