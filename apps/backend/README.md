# Inframeld backend

The Inframeld backend is a typed FastAPI application. It owns the HTTP API, its generated OpenAPI document, and the contract tests that prevent API drift.

## Quick start

For normal local development, run PostgreSQL and Kratos in Compose and the backend directly on your host.

From a clean checkout, install the committed dependencies from the repository root:

```bash
pnpm install --frozen-lockfile
uv sync --project apps/backend --locked
```

Use the Node and pnpm versions in the root `package.json` and the Python version in `apps/backend/.python-version`. CI's tool versions are pinned in `.github/workflows/ci.yml`.

### 1. Create your local environment

On your first setup, copy the example environment file:

```bash
cp apps/backend/.env.example apps/backend/.env
```

Keep your existing `.env` on subsequent setups.

Create the separate backend test configuration before running checks:

```bash
cp apps/backend/.env.test.example apps/backend/.env.test
```

Keep `.env.test` in the ignored local configuration; it is not committed.

### 2. Start PostgreSQL and Kratos

```bash
pnpm dev:db
```

### 3. Run migrations

```bash
pnpm --filter @inframeld/backend migrate
```

### 4. Start the backend

```bash
pnpm --filter @inframeld/backend dev
```

The API is now available at:

- API: http://127.0.0.1:8000
- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

When you're finished, stop the development containers with:

```bash
pnpm dev:db:down
```

The application database and Kratos identities are stored in separate named volumes and are preserved when the containers are stopped. Kratos's public endpoint is at http://127.0.0.1:14434.

---

## Architecture

The backend is a domain-first modular monolith. Top-level domain packages own their business state and rules; they are not separate services:

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
├── migrate.py    # operator-controlled migration entry point
└── main.py
```

### Package structure

Each business package follows onion architecture:

```text
knowledge/
├── domain/          # business rules and values
├── application/     # commands, queries, and application-owned ports
├── infrastructure/  # PostgreSQL and other external implementations
└── api/             # HTTP/MCP-facing adapters for this owner
```

Vertical slices live within these rings as use cases are implemented.

Only create files when the corresponding use case requires them. Do not pre-create generic repositories, services, or framework layers.

Dependencies point inward:

```text
api -> application -> domain
infrastructure -> application-owned ports
composition.py -> concrete implementations and configuration
```

### Shared code

`shared` is restricted to capabilities used across domains, such as:

- transport errors
- configuration
- database lifecycle
- jobs
- idempotency

It must not become a second owner of domain state.

The current health route is a cross-cutting HTTP adapter under `shared/http`. Domain and application code may not import it.

Shared technical capabilities use `domain/`, `application/`, and `infrastructure/` only where that separation is genuinely needed.

### Composition

`main.py` is the API entry point.

`migrate.py` is the separate, operator-controlled migration entry point.

`composition.py` is the API composition root. It constructs the application and explicitly wires concrete dependencies.

HTTP, the future worker, Studio, and MCP must invoke the same application use cases. They must not implement parallel business behavior.

These dependency rules are reviewed manually. Automated tests cover product behavior, API contracts, and integrations; do not add repository-structure, import-boundary, or composition-construction tests.

---

## Configuration

Runtime configuration is loaded from files under `apps/backend`:

- `.env` — local development
- `.env.test` — used when `INFRAMELD_ENVIRONMENT=test`
- `INFRAMELD_TEST_ENV_FILE` — selects another test environment file; relative paths are resolved from `apps/backend`
- `INFRAMELD_*` environment variables — override values loaded from dotenv files
- `.env.example` — documents local development database and Kratos defaults and may be copied to `.env`
- `.env.test.example` — documents isolated integration-test database and Kratos defaults and may be copied to `.env.test`

For the local Compose database, the relevant values are:

```dotenv
INFRAMELD_DATABASE__HOST=127.0.0.1
INFRAMELD_DATABASE__PORT=15432
INFRAMELD_DATABASE__NAME=inframeld
INFRAMELD_DATABASE__USER=inframeld
INFRAMELD_DATABASE__PASSWORD=inframeld-dev-only
INFRAMELD_KRATOS__PUBLIC_URL=http://127.0.0.1:14434
INFRAMELD_KRATOS__AUTHORITY=kratos:local
```

Do not commit `.env` or `.env.test`.

The development passwords and Kratos secrets are only for local Compose and must not be reused in production. Kratos settings are optional until the HTTP authentication dependency is wired into the backend application.

---

## Development services

The application PostgreSQL and Kratos services are managed by the root `compose.dev.yaml`. Kratos uses its own PostgreSQL service, `kratos_dev` database role, and `inframeld_kratos_postgres_data` volume, separate from the application database. Its public API is available on `127.0.0.1:14434`; its admin API stays inside the Compose network.

PostgreSQL is exposed to the host only at:

```text
127.0.0.1:15432
```

Inside the Compose network, PostgreSQL listens on its standard port `5432` and Kratos's public API listens at `http://kratos:4433`. A host-run backend uses the public URL from `.env`; the backend Compose service overrides that URL with the internal address. Both use the `kratos:local` identity authority. The Kratos migration runs before the service starts.

The development Kratos config enables password registration and login for local use. Its self-service UI URLs are placeholders until browser pages are implemented. Email delivery and deployment-level OIDC sign-in are not configured by this Compose setup.

### Development commands

Run these commands from the repository root:

```bash
pnpm dev:db               # Start PostgreSQL and Kratos in the background
pnpm dev:db:reset         # Recreate the application database; keep Kratos identities
pnpm dev:db:restart       # Restart PostgreSQL without removing its volume
pnpm dev:db:status        # Show development container status
pnpm dev:db:down          # Stop development containers, preserving both database volumes

pnpm dev:compose           # Start PostgreSQL, Kratos, and the backend
pnpm dev:compose:restart   # Restart all currently created Compose containers
pnpm dev:compose:down      # Stop all development containers, preserving both database volumes
```

These commands use [`scripts/dev-compose.sh`](../../scripts/dev-compose.sh), which automatically detects Podman Compose or Docker Compose.

`pnpm dev:db`, `pnpm dev:db:reset`, and `pnpm dev:compose` wait for PostgreSQL and Kratos readiness, retrying up to 60 times with a one-second interval. If a service does not become ready, the command exits with an error and reports the last readiness check.

The script can also be run directly:

```bash
./scripts/dev-compose.sh up
./scripts/dev-compose.sh reset-db
./scripts/dev-compose.sh all
./scripts/dev-compose.sh restart-db
./scripts/dev-compose.sh restart-all
./scripts/dev-compose.sh status
./scripts/dev-compose.sh check
./scripts/dev-compose.sh down
./scripts/dev-compose.sh test-db-up
./scripts/dev-compose.sh test-db-down
```

`check` verifies that the development PostgreSQL service is accepting connections. The integration test runner uses separate test-only PostgreSQL and Kratos services.

If PostgreSQL is unavailable, it reports the required dependency and startup commands.

Restart commands only apply to containers that Compose has already created. After running `down`, use the corresponding start command instead.

### Resetting the application database

Restarting or stopping either service does **not** remove its named volume.

To deliberately clear the application database and start with an empty one:

```bash
pnpm dev:db:reset
```

This:

1. Stops and removes the development Compose containers.
2. Keeps both named volumes and drops and recreates only the `inframeld` database.
3. Starts Kratos again with its existing identities.
4. Leaves the Compose backend stopped.

Migrations are not run automatically.

After resetting the database, run:

```bash
pnpm --filter @inframeld/backend migrate
```

before starting either the host API or the backend container.

### Running the backend in Compose

Running the backend image in Compose is an optional alternative to running the Python backend directly on your host.

The image uses the same source and locked dependencies as the host application, but it does not mount the source tree or run migrations during startup.

Start PostgreSQL and Kratos, apply application migrations, and then start the backend container:

```bash
pnpm dev:db
pnpm --filter @inframeld/backend migrate
pnpm dev:compose
```

The containerized API is available at:

- API: http://127.0.0.1:8001
- Swagger UI: http://127.0.0.1:8001/docs
- ReDoc: http://127.0.0.1:8001/redoc

Inside the Compose network, the backend connects to PostgreSQL using the `postgres` service on port `5432` and receives `http://kratos:4433` as its configured Kratos public URL.

A backend running directly on the host instead connects to PostgreSQL at `127.0.0.1:15432`. This allows you to use the same database setup whether you run the API on the host or in Compose.

`pnpm dev:compose` builds the backend image and starts the backend, PostgreSQL, and Kratos containers.

The backend binds inside the Compose network, with only its API port published to the host on the loopback interface.

Database startup checks schema compatibility and refuses to start against an unmigrated schema.

---

## Migrations

Migrations are explicit and operator-controlled. The API never runs migrations during startup.

Run migrations with:

```bash
pnpm --filter @inframeld/backend migrate
```

The supported command runs `inframeld_backend.migrate`.

Migrations are:

- synchronous
- protected by a PostgreSQL migration lock
- required before starting against a new or reset database

API startup checks schema compatibility and refuses to start against an incompatible schema.

Failed migrations return a nonzero exit status and emit a sanitized diagnostic through the shared logging infrastructure.

Programmatic `run_migrations()` calls continue to raise exceptions for their caller to handle.

Use the documented:

```bash
pnpm --filter @inframeld/backend migrate
```

command for operator execution.

Do not invoke Alembic directly for normal operation. Direct Alembic CLI invocations bypass the application's reporting boundary.

SQLAlchemy parameter hiding provides additional protection, but does not sanitize arbitrary database-driver messages.

Integration tests run the migration command automatically against `.env.test` before executing.

Do not add migrations to `pnpm dev` or API startup.

---

## Error handling

The shared HTTP error foundation implements [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457) using `application/problem+json`.

It provides:

- stable error codes
- safe public descriptions
- matching body/header request IDs
- transport-independent domain and application exceptions
- explicit mapping from application failures to supported public HTTP responses

The shared diagnostic renderer excludes exception messages, notes, source lines, and locals. Feature logs must also avoid submitted secrets.

When implementing a feature, read the [practical error-handling guide](../../docs/development/error-handling.md).

When changing the error-handling foundation itself, read the [maintainer reference](../../docs/development/error-handling-reference.md), which maps the implementation files and behavioral tests.

The backend and integration tests were reported passing at the 23 September 2026 error-handling closeout.

---

## Pagination

Shared HTTP pagination models provide:

- `limit` — defaults to `25`, maximum `100`
- `cursor` — optional, with syntax validation
- `items` — the returned resources
- `nextCursor` — cursor for the next page, when one exists

Read the [pagination guide](../../docs/development/pagination.md) before adding a list endpoint.

The shared models define the transport contract. Each owning feature remains responsible for:

- validating cursor contents
- choosing its ordering
- checking authorization on every page
- implementing the underlying query

---

## Checks

Run backend checks from the repository root:

```bash
pnpm check:backend
pnpm test:integration
```

`pnpm check:backend` runs backend formatting, linting, type checking, fast tests, and OpenAPI contract validation without PostgreSQL. It uses only the backend's locked Python environment and does not generate or install a Studio SDK.

### Unit and contract tests

`pnpm check:backend` keeps database integration tests skipped. Unit, health, and OpenAPI checks run without PostgreSQL.

### Integration tests

`pnpm test:integration` starts the application PostgreSQL and Kratos services from `compose.test.yaml`, waits for both, applies the application migrations, and runs all backend integration tests, including the real Kratos browser-flow test. Compose runs the Kratos migration before starting Kratos. The command stops the test services afterward and retains their test-only volumes. It forces the application test database's host, port, name, and credentials, so a database target in `.env.test` cannot redirect application migrations to the development database.

The application test PostgreSQL service listens on `127.0.0.1:15433`; Kratos's public endpoint listens on `127.0.0.1:14433`. Kratos uses its own PostgreSQL service, database role, and `inframeld_test_kratos_postgres_data` volume. Neither test database shares a volume with the development database at `127.0.0.1:15432`.

Application PostgreSQL integration tests create uniquely named tables and databases for their fixtures and clean them up after each test. The Kratos browser-flow test creates an identity with a unique email in Kratos's isolated test database; that identity remains in the retained test volume. Keep the database-specific values in `.env.test` aligned with `.env.test.example` when running tests directly with `pytest`.

---

## OpenAPI

The FastAPI application is the source of truth for the generated OpenAPI document.

Export the committed contract with:

```bash
pnpm --filter @inframeld/backend openapi
```

The generated document is stored at:

```text
contracts/openapi/v1/inframeld-v1.json
```

It is checked into the repository so clients and CI can review API contract changes as ordinary source changes.

### Problem responses

Routes declare applicable errors using:

```python
problem_responses(definition)
```

from `shared/http/problem_openapi.py`.

Composition installs its narrow media-type correction hook once. FastAPI still generates the native schema and reusable model components.

`/health` documents its possible `500` problem response.

JSON and multipart validation fixtures exercise `422` problems without exposing artificial production endpoints.

See the [error-handling maintainer reference](../../docs/development/error-handling-reference.md#openapi-and-client-compatibility) for the hook's scope and required upgrade checks.
