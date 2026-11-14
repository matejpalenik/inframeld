# Inframeld backend

The backend is a typed FastAPI application with Access and shared foundations. Knowledge, Indexing, Pipelines, Evaluation and Releases have accepted designs and domain scaffolds. Their documentation does not imply complete implementation.

Start with [local setup](../../docs/development/getting-started/local-setup.md). It covers locked dependencies, environment files, the separate fingerprint key, development services and explicit migrations. Then use [testing](../../docs/development/guides/testing.md) and [debugging](../../docs/development/guides/debugging.md).

Run commands from the repository root:

```bash
pnpm --filter @inframeld/backend dev
pnpm check:backend
pnpm test:integration
pnpm --filter @inframeld/backend openapi:check
```

These commands start the host API or run checks. They do not replace the setup and migration steps. Integration tests manage a private test stack and must run one invocation at a time.

The [production backend Dockerfile](Dockerfile) uses the same digest-pinned Python 3.13.18 Debian Trixie image in both stages so the installed packages see the same Python and system libraries at runtime. A separate digest pins uv 0.13.7 for the build. Application dependencies still come from `uv.lock`. The builder retrieves signed Debian packages, and the final image runs as UID and GID 10001. The complete Compose release and its runtime qualification are tracked in [#95](https://github.com/matejpalenik/inframeld/issues/95).

Development Compose includes Hydra with private administration. [Configure the official CLI client](../../docs/development/getting-started/local-setup.md#configure-the-cli-client) through `pnpm dev:oauth:configure`, or let `pnpm dev:compose` run that separate setup step before the API. Native lifetime settings live in root `.env`, separate from host API settings. The [isolated development check](../../docs/development/guides/testing.md#integration-tests) verifies setup without touching your existing databases. Account pages, Rust CLI interaction and packaged runtime delivery remain unfinished.

For a new component, follow [the contributor example](../../docs/development/guides/adding-a-backend-feature.md) and mandatory [Coding Standards](../../.agents/skills/inframeld-coding-standards/SKILL.md). Reusable pure conversion/validation utilities default to named static classes. Injected services, private helpers, fixtures and framework callables retain their documented roles.

Access recovery admission/completion and credential-state initialization share [identity coordination](../../.agents/skills/inframeld-access-models/references/identity-admission-coordination.md). The coordinator uses each operation's existing transaction before organization locks. Invitation activation remains unfinished and must reuse the same coordinator.

[Contracts and data](../../docs/development/guides/contracts-and-data.md) routes to implemented types, generated HTTP schema and migrations. [The architecture introduction](../../docs/ARCHITECTURE.md) explains the accepted product. [AGENTS.md](../../AGENTS.md) distinguishes read-only guidance from requested implementation.

Credential management for a Model Connection uses a distinct optional [provider credential key and trusted identity](../../docs/development/getting-started/local-setup.md#provider-credential-encryption-key). The dedicated API requires the current human Manage action. Saving or removing a key is conditional on its credential revision and produces a safe original receipt. Migration `0036_provider_credentials` preserves the slot and its latest revision after removal.

## Retained deletion-status reader

`GET /v1/deletions/status?operationId=...` reads a content-free observation for the currently eligible original initiating human. Existing Kratos session and human OAuth authentication remain in force. Ordinary Project membership may have disappeared. Another eligible human receives the same unresolved result as missing history, while invalid credentials and current ineligibility remain authentication/authorization failures. [Read retained deletion status](../docs/src/app/guides/read-deletion-status/page.mdx) covers HTTP/generated-client examples and recovery.

Use the normal setup and migration path above. Migration `0013_deletion_status` follows `0010_durable_jobs` and adds the original binding and owner-observation tables. Later metadata migrations build on this foundation.

`INFRAMELD_DELETION_STATUS_RETENTION__DAYS` selects the profile for future bindings, with a 30-day default and a supported range of 1–90 whole days. A shorter period needs the existing reviewed policy update. Development Compose passes the same setting to the API. Changing it does not rewrite an existing captured profile or extend established expiry. An unfinished cleanup obligation is separate from settled-status expiry. The [owning retention policy](../../.agents/skills/inframeld-knowledge/references/decision-retention-erasure-policy.md#approved-resolution) explains that boundary.

This component reads retained facts. It does not deliver authentic Delete-project admission, application/key shutdown or physical erasure. Seeded database/native-auth and controlled generated-client cases establish the reader boundary, not those producer workflows. No deletion-status CLI command is delivered here.

## Project metadata

Existing Projects support `GET /v1/projects/{project_id}/metadata`, `PATCH /v1/projects/{project_id}/metadata` and `GET /v1/projects/by-name/{name}`. [Name and rename an existing Project](../../apps/docs/src/app/guides/name-and-rename-project/page.mdx) explains exact selectors, legacy labels, stable IDs and original-operation recovery. Reads use current visibility. Changes additionally require human-only `edit-project-metadata` and the reviewed metadata revision, separate from the Project Access revision.

Schema `0014_project_metadata` preserves existing `projects.name` text as the legacy label and adds a separate nullable selector. [Restricted metadata-authority repair](../../docs/development/operations/project-metadata-repair.md) consumes protected stdin through `inframeld-maintenance`, with real identity verification and original receipts. Its proof-acquisition prerequisite lacks a qualified UI/client journey, so this does not establish an end-to-end first-grant walkthrough. [Ordinary Project creation](../docs/src/app/guides/create-project/page.mdx) through HTTP or a generated SDK saves all eighteen explicit creator assignments with the Project, creator membership, audit and original result. Private-starter provisioning remains unfinished under #27, and the complete supported account-to-API procedure and human acceptance remain unfinished under [#313](https://github.com/matejpalenik/inframeld/issues/313).

## Project membership read

`GET /v1/projects/{project_id}/members` returns one bounded page of stored memberships under current human eligibility, Project membership and permission to use `manage-project-members`. Delegation authority is not required. [List Project members](../docs/src/app/guides/list-project-members/page.mdx) explains HTTP/generated-client use, page size, opaque continuation and per-page authorization/revision. Stored inactive memberships remain visible to the authorized reader, without emails, grants or totals. This read uses existing schema and does not add or remove members.

The initial real starting case is the creator's membership from ordinary Project creation. Full membership mutation and safe handover remain unfinished in #224. [Human qualification #319](https://github.com/matejpalenik/inframeld/issues/319) needs a supported authentication/setup procedure and later multi-member preparation. Backend and generated-client tests do not establish that human journey.

## Ordinary application worker

`python -m inframeld_backend.application_worker` starts the shared PostgreSQL-backed worker without an HTTP listener. Development Compose exposes it through the opt-in `jobs` profile. Its default production handler registry is empty, and there is no generic job API or CLI. [Run the ordinary application worker](../../docs/development/operations/application-jobs.md) covers explicit schema migration, environment loading, settings, events and safe shutdown.

## Private recovery notifications

`inframeld_backend.recovery_main:app` serves the three private v2 Kratos callbacks on port 8081. It requires only database configuration, `INFRAMELD_RECOVERY__AUTHORITY` and protected hook-key files. It has no public documentation endpoint and is not mounted in the product API.

[Local setup](../../docs/development/getting-started/local-setup.md#private-recovery-callbacks) explains explicit activation. [The owning contract](../../.agents/skills/inframeld-access-models/references/private-recovery-handoff.md#implemented-private-delivery) explains receipts, native association and replay. Migration `0006_identity_recovery_delivery` adds evidence and the original cleanup handoff/run. The callback process performs no Hydra cleanup or block release. `python -m inframeld_backend.recovery_worker` now executes the handoff and proof-backed completion in a separate process. Migration 0007 adds fenced attempts and proof. Enable both processes explicitly after migration. Migration 0008 adds the immutable maintenance receipt. The `resume-recovery-cleanup` mode of `inframeld-maintenance` authorizes an additional bounded run after an operator repairs the cause. [The runbook](../../docs/development/getting-started/local-setup.md#resume-recovery-cleanup) explains its protected stdin and same-request replay.

The recovery worker requires only `INFRAMELD_DATABASE__*`, `INFRAMELD_RECOVERY_CLEANUP__AUTHORITY` and `INFRAMELD_RECOVERY_CLEANUP__HYDRA_ADMIN_URL`. It has no listener or hook-key requirement. [Local setup](../../docs/development/getting-started/local-setup.md#private-recovery-callbacks) covers isolated startup and [the owning completion guide](../../.agents/skills/inframeld-access-models/references/recovery-completion.md#implemented-execution-and-proof-backed-completion) explains deadlines, leases, retry and release.
