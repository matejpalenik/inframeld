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

For a new component, follow [the contributor example](../../docs/development/guides/adding-a-backend-feature.md) and mandatory [Coding Standards](../../.agents/skills/inframeld-coding-standards/SKILL.md). Reusable pure conversion/validation utilities default to named static classes. Injected services, private helpers, fixtures and framework callables retain their documented roles.

[Contracts and data](../../docs/development/guides/contracts-and-data.md) routes to implemented types, generated HTTP schema and migrations. [The architecture introduction](../../docs/ARCHITECTURE.md) explains the accepted product. [AGENTS.md](../../AGENTS.md) preserves read-only guidance and exact write confirmation.
