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
| Operate, upgrade or restore an installation | [Runtime](operations/runtime-and-networking.md), [upgrades](operations/upgrades.md), [backup and restore](operations/backup-and-restore.md) |
| Understand a public HTTP problem | [Problem catalogue](error-handling.md) |
| Finish or document a change | [Definition of Done](definition-of-done.md) and [documentation maintenance](documentation-maintenance.md) |

<a id="find-the-detailed-owner"></a>

## Find the detailed owner

The skill references are written for people as well as coding agents. They own detailed accepted behavior and architecture. Read a focused workflow directly. You do not need to load every skill or the full glossary first.

- [Access](../../.agents/skills/inframeld-access-models/SKILL.md): identity, authentication, grants, recovery and credential protection.
- [Knowledge](../../.agents/skills/inframeld-knowledge/SKILL.md): documents, immutable versions, collections and source synchronization.
- [Indexing](../../.agents/skills/inframeld-indexing/SKILL.md): parsing, embeddings, verified search data and cleanup.
- [Pipelines](../../.agents/skills/inframeld-pipelines/SKILL.md): configuration, ordinary execution, receipts, feedback and tracing.
- [Evaluation](../../.agents/skills/inframeld-evaluation/SKILL.md): cases, frozen tests, fresh comparisons and protected evidence.
- [Releases](../../.agents/skills/inframeld-releases/SKILL.md): serving selection, Automatic/Manual transitions and rollback.
- [Application Contracts](../../.agents/skills/inframeld-application-contracts/SKILL.md): transactions, jobs, transports, CLI and ModelGateway.
- [Coding Standards](../../.agents/skills/inframeld-coding-standards/SKILL.md): component placement and complete backend examples. Other languages keep their own guidance.
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
