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

Development Compose includes Hydra with private administration. [Configure the official CLI client](../../docs/development/getting-started/local-setup.md#configure-the-cli-client) through `pnpm dev:oauth:configure`, or let `pnpm dev:compose` run that separate setup step before the API. Native lifetime settings live in root `.env`, separate from host API settings. The [isolated development check](../../docs/development/guides/testing.md#integration-tests) verifies setup without touching your existing databases. Account pages, Rust CLI interaction and packaged runtime delivery remain unfinished.

For a new component, follow [the contributor example](../../docs/development/guides/adding-a-backend-feature.md) and mandatory [Coding Standards](../../.agents/skills/inframeld-coding-standards/SKILL.md). Reusable pure conversion/validation utilities default to named static classes. Injected services, private helpers, fixtures and framework callables retain their documented roles.

Access recovery admission/completion and credential-state initialization share [identity coordination](../../.agents/skills/inframeld-access-models/references/identity-admission-coordination.md). The coordinator uses each operation's existing transaction before organization locks. Invitation activation remains unfinished and must reuse the same coordinator.

[Contracts and data](../../docs/development/guides/contracts-and-data.md) routes to implemented types, generated HTTP schema and migrations. [The architecture introduction](../../docs/ARCHITECTURE.md) explains the accepted product. [AGENTS.md](../../AGENTS.md) distinguishes read-only guidance from requested implementation.

## Ordinary application worker

`python -m inframeld_backend.application_worker` starts the shared PostgreSQL-backed worker without an HTTP listener. Development Compose exposes it through the opt-in `jobs` profile. Its default production handler registry is empty, and there is no generic job API or CLI. [Run the ordinary application worker](../../docs/development/operations/application-jobs.md) covers explicit schema migration, environment loading, settings, events and safe shutdown.

## Private recovery notifications

`inframeld_backend.recovery_main:app` serves the three private v2 Kratos callbacks on port 8081. It requires only database configuration, `INFRAMELD_RECOVERY__AUTHORITY` and protected hook-key files. It has no public documentation endpoint and is not mounted in the product API.

[Local setup](../../docs/development/getting-started/local-setup.md#private-recovery-callbacks) explains explicit activation. [The owning contract](../../.agents/skills/inframeld-access-models/references/private-recovery-handoff.md#implemented-private-delivery) explains receipts, native association and replay. Migration `0006_identity_recovery_delivery` adds evidence and the original cleanup handoff/run. The callback process performs no Hydra cleanup or block release. `python -m inframeld_backend.recovery_worker` now executes the handoff and proof-backed completion in a separate process. Migration 0007 adds fenced attempts and proof. Enable both processes explicitly after migration. Migration 0008 adds the immutable maintenance receipt. `inframeld-maintenance` authorizes an additional bounded run after an operator repairs the cause. [The runbook](../../docs/development/getting-started/local-setup.md#resume-recovery-cleanup) explains its protected stdin and same-request replay.

The recovery worker requires only `INFRAMELD_DATABASE__*`, `INFRAMELD_RECOVERY_CLEANUP__AUTHORITY` and `INFRAMELD_RECOVERY_CLEANUP__HYDRA_ADMIN_URL`. It has no listener or hook-key requirement. [Local setup](../../docs/development/getting-started/local-setup.md#private-recovery-callbacks) covers isolated startup and [the owning completion guide](../../.agents/skills/inframeld-access-models/references/recovery-completion.md#implemented-execution-and-proof-backed-completion) explains deadlines, leases, retry and release.
