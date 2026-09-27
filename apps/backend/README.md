# Inframeld backend

The Inframeld backend is a typed FastAPI application. It owns the HTTP API, its generated OpenAPI document, and the contract tests that prevent API drift.

## Quick start

For normal local development, run PostgreSQL, Kratos, and Mailpit in Compose and the backend directly on your host.

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

[Create the idempotency fingerprint key](#idempotency-fingerprint-key) and set its absolute path in both local environment files before running migrations or starting the backend.

### 2. Start PostgreSQL, Kratos, and Mailpit

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

The application database and Kratos identities are stored in separate named volumes and are preserved when the containers are stopped. Kratos's public endpoint is at http://127.0.0.1:14434. Mailpit's development inbox is at http://127.0.0.1:18024.

---

## Architecture and component map

The backend follows **domain → layer → component role**. Start with the [component map, record conventions, and worked authentication flow](../../docs/development/application-structure.md#component-conventions) before adding a component.

```text
src/inframeld_backend/
├── bootstrap/                 # factory, aggregate settings, assembly, lifecycle
├── access/
│   ├── domain/                # entities, value_objects, enums, policy_inputs, policies
│   ├── application/           # services, protocols, dtos, value_objects
│   ├── http/                  # routes, dependencies, responses
│   └── infrastructure/        # readers, verifiers, rows, settings, types
├── shared/
│   ├── domain/                # errors, validation
│   ├── application/           # errors, enums, dtos, value_objects
│   ├── http/                  # handlers, responses, builders, mappers, middleware, etc.
│   └── infrastructure/        # resources, migrations, logging, diagnostics, settings, etc.
├── main.py
└── migrate.py
```

Knowledge, Indexing, Pipelines, Evaluation, and Releases retain their domain scaffolds. Add role folders with actual workflows. Shared code contains genuinely shared technical responsibilities.

Application services own business orchestration through explicit protocols. Domain entities, value objects, and named policy classes express rules without I/O. Policies expose pure static methods; ordinary conversion and validation helpers can remain functions. HTTP, PostgreSQL, and provider adapters convert values at their boundaries. Bootstrap constructs concrete dependencies and owns resource lifecycle.

Application records use the `DTO` suffix, such as `VerifiedHumanIdentityDTO`. Dedicated policy inputs use `PolicyInput`, such as `ActionAuthorizationPolicyInput`. `ProjectActionFactsDTO` is a reader result, despite the word “Facts.” Use standard frozen, slotted dataclasses; no record marker protocols or custom decorators. Keep docstrings where they explain meaningful behavior or ownership, and omit repetitive boilerplate.

`HumanSessionDependency` extracts the cookie and calls `HumanSessionAuthenticator`. `HumanSessionAuthenticationService` verifies the provider session, reads the exact linked principal, applies `HumanAuthenticationPolicy`, and returns `AccessContextDTO`. The route serializes its ID into the existing `principalId` response. `ActionAuthorizationService` separately checks project visibility and the exact action grant through `ProjectVisibilityPolicy` and `ActionAuthorizationPolicy`.

Application construction and OpenAPI export perform no network calls. The lifespan owns database startup/shutdown and actual Kratos SDK pool cleanup, including failed startup. Authentication adapters are shared per application, but each identity lookup opens its own short session after provider verification. Authorization readers use the caller's transaction session. This organization change preserves that lifecycle.

UUID identities remain runtime value objects. ORM columns remain UUIDs and enum columns perform real conversion. The immutable `Principal` holds account state; `AccessContextDTO` carries only its identity. The [data model](../../docs/development/data-model.md#implemented-principal-model) explains these distinctions.

Architecture and naming are reviewed manually. Unit tests mirror production roles; integration tests remain grouped by scenario. Automated checks cover behavior, typing, contracts, and integration outcomes.

---

## Configuration

`bootstrap/application_settings.py` aggregates `ApplicationSettings`. `KratosSettings`, `CSRFSettings`, and `DatabaseSettings` live in their owners’ infrastructure `settings` packages; logging value definitions live in shared infrastructure `types`.

Runtime configuration is loaded from files under `apps/backend`:

- `.env` — local development
- `.env.test` — used when `INFRAMELD_ENVIRONMENT=test`
- `INFRAMELD_TEST_ENV_FILE` — selects another test environment file; relative paths are resolved from `apps/backend`
- `INFRAMELD_*` environment variables — override values loaded from dotenv files
- `.env.example` — documents local development database, Kratos, CSRF, and fingerprint-key path settings and may be copied to `.env`
- `.env.test.example` — documents isolated integration-test database, Kratos defaults, and the fingerprint-key path and may be copied to `.env.test`

### Idempotency fingerprint key

`RequestFingerprintService` uses a deployment HMAC key to calculate fingerprints for requests containing secrets. PostgreSQL stores the resulting fingerprints and idempotency reservations, not the HMAC key. Keep the key stable while those reservations are retained, and keep it separate from the provider-credential encryption key. See [Background jobs, retries, and competing changes](../../docs/development/jobs-and-idempotency.md#fingerprint-secret-bearing-requests-without-exposing-the-secret) for the request rule.

For local macOS development with Podman, create one raw 32-byte key outside the source checkout, under your home directory:

```bash
python3 - <<'PY'
import os
from pathlib import Path
from secrets import token_bytes

os.umask(0o077)
key_file = Path.home() / ".config/inframeld/secrets/idempotency_fingerprint_hmac.key"
key_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "wb") as output:
    output.write(token_bytes(32))
PY
```

On a Linux VM with rootful Docker, use the host-managed path `/etc/inframeld/secrets/idempotency_fingerprint_hmac.key` instead. Provision it as an administrator for the backend image's UID 10001:

```bash
sudo python3 - <<'PY'
import os
from pathlib import Path
from secrets import token_bytes

os.umask(0o077)
key_file = Path("/etc/inframeld/secrets/idempotency_fingerprint_hmac.key")
key_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "wb") as output:
    output.write(token_bytes(32))
os.chown(key_file, 10001, 10001)
os.chmod(key_file, 0o400)
PY
```

Both commands print no key material and refuse to overwrite an existing file. If an earlier setup already has a fingerprint key, move that exact file to the new host path instead of generating another. Include the host-managed file in the installation's [protected backup set](../../docs/development/upgrades-and-recovery.md#backup). Restore the same key on a replacement VM; do not generate a new one on restart or after losing the file.

Set the absolute host path in both `apps/backend/.env` and `apps/backend/.env.test`. The checked-in examples show the Linux VM path:

```dotenv
INFRAMELD_REQUEST_FINGERPRINT__KEY_FILE=/etc/inframeld/secrets/idempotency_fingerprint_hmac.key
```

On macOS, use the absolute path under your home directory instead. For the Compose backend, also set `INFRAMELD_FINGERPRINT_KEY_HOST_FILE` in the repository-root `.env` file to that same host path. [Podman Machine](https://docs.podman.io/en/latest/markdown/podman-machine-init.1.html) shares the home directory by default; it does not automatically share macOS `/etc`.

Only paths go in the environment files. For `pnpm dev:compose`, `compose.dev.yaml` defaults to the Linux VM's `/etc/inframeld/secrets` host file; the root `.env` value overrides that source on macOS. Compose mounts the selected file read-only as `/run/secrets/idempotency_fingerprint_hmac` and sets that container path automatically. The host-run backend and the container's UID 10001 must each be able to read the file when they run. [File-backed Compose secrets](https://docs.docker.com/reference/compose-file/services/#secrets) keep host ownership and permission bits; grant the required runtime identities read access through restricted ownership, group membership, or ACLs. Do not make the key world-readable. Use a separate key for a separate installation, including an isolated test deployment.

Configuration currently validates the path, and the file reader validates its contents when called. No production operation loads the fingerprint key at startup yet.

For a backend running on the host with local Compose services, the relevant values are:

```dotenv
INFRAMELD_DATABASE__HOST=127.0.0.1
INFRAMELD_DATABASE__PORT=15432
INFRAMELD_DATABASE__NAME=inframeld
INFRAMELD_DATABASE__USER=inframeld
INFRAMELD_DATABASE__PASSWORD=inframeld-dev-only
INFRAMELD_KRATOS__PUBLIC_URL=http://127.0.0.1:14434
INFRAMELD_KRATOS__AUTHORITY=kratos:local
INFRAMELD_CSRF__TRUSTED_ORIGINS='["http://127.0.0.1:8000"]'
```

`INFRAMELD_CSRF__TRUSTED_ORIGINS` is a JSON array of exact browser origins: scheme, host, and optional port, without a path. The host-run example permits requests originating from `http://127.0.0.1:8000`; `compose.dev.yaml` uses `http://127.0.0.1:8001`, its published backend port. An omitted or empty list denies cookie-authenticated writes.

After authentication, unsafe requests also need `X-Inframeld-CSRF: 1` and a matching `Origin` header. This is Inframeld's HTTP protection; Kratos checks its own CSRF values during browser account flows. The [Access guide](../../docs/development/access-control.md#implemented-human-authentication) describes the implemented boundary and its test coverage.

The web scaffold currently runs on `localhost:3000`, while these backend and Kratos examples use `127.0.0.1`. Browser integration still needs a consistent hostname and routing so the Kratos cookie reaches the backend. The trusted-origin list alone does not configure that routing.

Do not commit `.env` or `.env.test`.

The development passwords and Kratos secrets are only for local Compose and must not be reused in production. Kratos settings remain optional at startup; without them, the session route returns 503.

---

## Development services

The application PostgreSQL, Kratos, and Mailpit services are managed by the root `compose.dev.yaml`. Kratos uses its own PostgreSQL service, `kratos_dev` database role, and `inframeld_kratos_postgres_data` volume, separate from the application database. Its public API is available on `127.0.0.1:14434`; its admin API stays inside the Compose network. Mailpit's SMTP port stays inside that network, while its inbox UI is exposed only on the host loopback interface at `127.0.0.1:18024`.

PostgreSQL is exposed to the host only at:

```text
127.0.0.1:15432
```

Inside the Compose network, PostgreSQL listens on its standard port `5432` and Kratos's public API listens at `http://kratos:4433`. A host-run backend uses the public URL from `.env`; the backend Compose service overrides that URL with the internal address. Both use the `kratos:local` identity authority. The Kratos migration runs before the service starts.

The development Kratos config enables password registration, login, and code-based recovery. Kratos sends development email to Mailpit; view captured messages at `http://127.0.0.1:18024`. Its self-service UI URLs are placeholders until browser pages are implemented. Mailpit is for local development; an operator deployment needs its own SMTP configuration. Deployment-level OIDC sign-in is not configured by this Compose setup.

To enable company OIDC locally, register `http://127.0.0.1:14434/self-service/methods/oidc/callback/company` as the provider's redirect URI. Copy the development config to a private file, which Git ignores:

```bash
cp config/kratos/dev.yaml config/kratos/dev.local.yaml
```

In `dev.local.yaml`, add this block under the existing `selfservice.methods` key, using your provider's values:

<!-- prettier-ignore -->
```yaml
    oidc:
      enabled: true
      config:
        providers:
          - id: company
            provider: generic
            client_id: YOUR_CLIENT_ID
            client_secret: YOUR_CLIENT_SECRET
            issuer_url: https://YOUR_PROVIDER_ISSUER
            mapper_url: file:///etc/config/kratos/oidc.email.jsonnet
            claims_source: id_token
            scope:
              - openid
              - email
```

Under the existing `selfservice.flows.registration.after` key in that same file, add the OIDC session hook:

<!-- prettier-ignore -->
```yaml
        oidc:
          hooks:
            - hook: session
```

The same settings are in [`oidc.example.yaml`](../../config/kratos/oidc.example.yaml). Finally, under `kratos` in `compose.dev.yaml`, comment out the default `command` and uncomment the `dev.local.yaml` command, then restart the services:

```bash
pnpm dev:db:down
pnpm dev:db
```

### Development commands

Run these commands from the repository root:

```bash
pnpm dev:db               # Start PostgreSQL, Kratos, and Mailpit in the background
pnpm dev:db:reset         # Recreate the application database; keep Kratos identities
pnpm dev:db:restart       # Restart PostgreSQL without removing its volume
pnpm dev:db:status        # Show development container status
pnpm dev:db:down          # Stop development containers, preserving both database volumes

pnpm dev:compose           # Start PostgreSQL, Kratos, Mailpit, and the backend
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
./scripts/dev-compose.sh test-services-up
./scripts/dev-compose.sh test-services-down
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

Start PostgreSQL, Kratos, and Mailpit, apply application migrations, and then start the backend container:

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

The reorganization was checked on 26 September 2026 with `pnpm check:backend` (190 passed, 50 service-dependent tests skipped) and `pnpm test:integration` (50 passed). Formatting, strict Pyright, and OpenAPI drift checks passed. The existing Starlette/AnyIO deprecation warning remains.

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

`pnpm check:backend` keeps service-dependent integration tests skipped. Unit directories mirror production capabilities; strict Pyright also requires explicit `@override`. Unit, health, and OpenAPI checks run without PostgreSQL.

### Integration tests

CI runs the same `pnpm test:integration` command; there is no separate database-only CI suite.

`pnpm test:integration` starts the application PostgreSQL, two Kratos test processes, Mailpit, and the mock OIDC provider from `compose.test.yaml`, waits for the required services, applies the application migrations, and runs all backend integration tests. The real browser tests cover registration, password login, session expiry, logout, disabled identities, code recovery, OIDC login, and password-confirmed OIDC account linking. They also check that matching email alone does not link an account. Compose runs the Kratos migration before starting either Kratos process. The command stops the test services afterward and retains their test-only volumes. It forces the application test database's host, port, name, and credentials, so a database target in `.env.test` cannot redirect application migrations to the development database.

The application test PostgreSQL service listens on `127.0.0.1:15433`. Standard test Kratos listens on `127.0.0.1:14433`; an expiry-only Kratos process listens on `127.0.0.1:14435` and issues 15-second sessions. Both Kratos processes share the separate test Kratos PostgreSQL service, database role, and `inframeld_test_kratos_postgres_data` volume. Their admin endpoints stay inside Compose. Neither test database shares a volume with the development database at `127.0.0.1:15432`.

Integration scenarios live under `tests/integration/access`, `postgres`, `kratos`, and `observability`. Typed seed builders, validated browser-flow helpers, and isolated database provisioning live under `tests/support`. Application PostgreSQL tests use temporary databases and Alembic-created fixture tables, cleaned up after each test. The Kratos browser-flow test creates an identity with a unique email in Kratos's isolated test database; that identity remains in the retained test volume. Keep the database-specific values in `.env.test` aligned with `.env.test.example` when running tests directly with `pytest`.

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

from `shared/http/openapi/problem_openapi.py`.

Composition installs its narrow media-type correction hook once. FastAPI still generates the native schema and reusable model components.

`/health` documents its possible `500` problem response.

JSON and multipart validation fixtures exercise `422` problems without exposing artificial production endpoints.

See the [error-handling maintainer reference](../../docs/development/error-handling-reference.md#openapi-and-client-compatibility) for the hook's scope and required upgrade checks.
