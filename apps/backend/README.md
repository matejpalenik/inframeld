# Inframeld backend

The backend is a typed FastAPI application. It owns the HTTP API, its generated OpenAPI document, and the contract tests that prevent API drift.

## Backend structure

The backend is a domain-first modular monolith. The top-level domain packages own business state and rules; they are not separate services:

```text
src/inframeld_backend/
├── access/       # principals, project scope, grants, authorization
├── knowledge/    # sources, document versions, collections, memberships
├── indexing/     # processing, embeddings, generations, materializations
├── pipelines/    # immutable RAG configuration, queries, receipts, feedback
├── evaluation/   # offline cases, runs, evidence, metrics, comparisons
├── releases/     # deployments, cohorts, promotion, rejection, rollback
├── shared/       # cross-cutting capabilities; no business-state ownership
├── composition.py
└── main.py
```

Each business package uses the onion-architecture rings below:

```text
knowledge/
├── domain/          # business rules and values
├── application/     # commands, queries, and application-owned ports
├── infrastructure/  # PostgreSQL and other external implementations
└── api/             # HTTP/MCP-facing adapters for this owner
```

Vertical slices live within those rings when a use case is implemented. Only create the slice's files when the corresponding use case is being implemented; do not pre-create generic repositories, services, or framework layers. Within a module, dependencies point inward:

```text
api -> application -> domain
infrastructure -> application-owned ports
composition.py -> concrete implementations and configuration
```

`shared` is restricted to capabilities used across domains, such as transport errors, configuration, database lifecycle, jobs, and idempotency. It must not become a second owner of domain state. The current health route is a cross-cutting HTTP adapter under `shared/http`; domain and application code may not import it. Shared technical capabilities use `domain/`, `application/`, and `infrastructure/` only where that separation is genuinely needed.

`main.py` is the process entry point. `composition.py` is the composition root: it constructs the application and explicitly wires concrete dependencies. HTTP, the future worker, Studio, and MCP must invoke the same application use cases; they must not implement parallel business behavior.

Architecture tests under `tests/architecture` protect these dependency rules. They use static import checks and fixtures that prove forbidden dependencies are rejected.

## Development

From the repository root:

```bash
pnpm dev:db
pnpm --filter @inframeld/backend migrate
pnpm --filter @inframeld/backend dev
```

The development PostgreSQL service is managed by the root `compose.dev.yaml` file. The database is exposed only on the local host at `127.0.0.1:15432`; PostgreSQL still listens on port `5432` inside the container. The backend connects to the host-mapped port.

The API is available at <http://127.0.0.1:8000>. FastAPI's interactive documentation is available at `/docs` and `/redoc`.

## Configuration

Runtime configuration is loaded from files under `apps/backend`:

- `.env` is used for local development.
- `.env.test` is used when `INFRAMELD_ENVIRONMENT=test`.
- `INFRAMELD_TEST_ENV_FILE` can select another test environment file. Relative paths are resolved from `apps/backend`.
- `INFRAMELD_*` environment variables override values from dotenv files.
- `.env.example` documents the non-secret development defaults and may be copied to `.env` or `.env.test`.

For the Compose database, the relevant local values are:

```dotenv
INFRAMELD_DATABASE__HOST=127.0.0.1
INFRAMELD_DATABASE__PORT=15432
INFRAMELD_DATABASE__NAME=inframeld
INFRAMELD_DATABASE__USER=inframeld
INFRAMELD_DATABASE__PASSWORD=inframeld-dev-only
```

Do not commit `.env` or `.env.test`. The development password above is only a local Compose credential and must not be reused in production.

## Database

Run these commands from the repository root:

```bash
pnpm dev:db          # Start PostgreSQL in the background
pnpm dev:db:status   # Show the PostgreSQL container status
pnpm dev:db:down     # Stop PostgreSQL and preserve its data volume
```

These commands use [`scripts/dev-compose.sh`](../../scripts/dev-compose.sh), which detects Podman Compose or Docker Compose. The script can also be run directly:

```bash
./scripts/dev-compose.sh up
./scripts/dev-compose.sh status
./scripts/dev-compose.sh check
./scripts/dev-compose.sh down
```

`check` verifies that PostgreSQL is accepting connections and is used before the integration test suite. It reports the required dependency and startup commands if PostgreSQL is unavailable.

The normal development workflow is:

```bash
pnpm dev:db
pnpm dev
```

Stop the database when finished with:

```bash
pnpm dev:db:down
```

This preserves the named PostgreSQL volume. Removing the volume is a destructive reset and should only be done deliberately with the Compose `down -v` command.

### Migrations

Before you can run the development app, you need to start the migrations in the dev database.

```bash
pnpm --filter @inframeld/backend migrate
```

Migrations are operator-controlled, synchronous, and protected by a PostgreSQL migration lock. API startup checks schema compatibility but never runs migrations.

`pnpm test:integration` runs this migration command automatically against `.env.test` before executing integration tests.

Do not add migrations to `pnpm dev` or API startup.

## Checks

```bash
pnpm --filter @inframeld/backend format:check
pnpm --filter @inframeld/backend lint
pnpm --filter @inframeld/backend typecheck
pnpm --filter @inframeld/backend test
pnpm --filter @inframeld/backend openapi:check
pnpm test:integration
```

`pnpm test` keeps the database integration tests skipped so unit, health, and OpenAPI tests can run without PostgreSQL. `pnpm test:integration` first checks the Compose PostgreSQL dependency, then runs the real PostgreSQL commit, rollback, constraint, and session-isolation tests. Ensure `apps/backend/.env.test` points to the Compose database before running it.

## OpenAPI

The application is the source of truth for the generated OpenAPI document. Export the committed contract with:

```bash
pnpm --filter @inframeld/backend openapi
```

The exported document lives at `contracts/openapi/v1/inframeld-v1.json` and is checked into the repository so clients and CI can review contract changes as ordinary source changes.
