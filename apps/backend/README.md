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
│   └── infrastructure/        # readers, revokers, verifiers, rows, settings, types
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

Follow the [service-writing guide](../../docs/development/application-structure.md#service-writing-guide) for new and suggested services. It uses the implemented grant workflow to show rich aggregate behavior, direct dependencies, authorization/retry/transaction ordering and stable domain-error translation. It also explains the appropriate variations for creation, reads and provider workflows. [AGENTS.md](../../AGENTS.md) requires generated code to follow this convention.

CQRS command and query inputs use `Command` and `Query` without a `DTO` suffix, such as `AssignProjectUseOnlyGrantCommand` and `GetProjectQuery`. Place them in the owning domain's `application/commands/` and `application/queries/` folders when a real workflow needs them. They carry immutable inputs and may validate their own fields without I/O. Execution remains in application services, and direct typed parameters are still valid. Other application transfer records use `DTO`, including results, projections, and metadata such as `VerifiedHumanIdentityDTO` and `CommandContextDTO`. Dedicated policy inputs use `PolicyInput`, such as `ActionAuthorizationPolicyInput`. `ProjectActionFactsDTO` is a reader result, despite the word “Facts.” Use standard frozen, slotted dataclasses without custom decorators. The agreed `Command` base classifies changes, while the field-based `ProjectCommand` Protocol requires a project ID. Concrete project Commands explicitly inherit both and declare their own fields. Authorization DTOs implement the generic `AuthorizedOperationScope` field contract. These narrow exceptions are explained in [ADR-0066](../../docs/adr/ADR-0066-use-typed-operation-contexts-and-command-classification.md). The [component conventions](../../docs/development/application-structure.md#component-conventions) explain the distinction. Keep docstrings where they explain meaningful behavior or ownership, and omit repetitive boilerplate. Authorization uses the abstract `Authorizer[RequestType, ResultType].require_authorization(access, request)` convention through specific permission-family Protocols. Access-owned authorization requests remain separate from business Commands. Reuse a family across operations, preserve its policy checks and verify returned scope before reservation or replay. See [ADR-0067](../../docs/adr/ADR-0067-standardize-authorization-capabilities-with-typed-requests.md) and the [typed authorization guide](../../docs/development/application-structure.md#typed-authorization).

`HumanSessionDependency` chooses a Kratos cookie or human bearer credential before verification. The cookie path calls `HumanSessionAuthenticationService`. The bearer path calls `HumanAccessTokenAuthenticationService`, which verifies the access token through Hydra and then checks the current Kratos identity. Both paths read the same local identity link and apply `HumanAuthenticationPolicy`. They return `AccessContextDTO` with only the principal ID, which the session route serializes as the existing `principalId` field. `ActionAuthorizationService` separately checks project visibility and the exact action grant through `ProjectVisibilityPolicy` and `ActionAuthorizationPolicy`.

Application construction and OpenAPI export perform no network calls. Bootstrap owns the Kratos public client and, when Hydra is configured, the Kratos admin and Hydra admin clients. The lifespan owns database startup/shutdown and clears all configured SDK pools, including failed startup or shutdown. Authentication adapters are shared per application, but each identity lookup opens its own short session after provider verification. Authorization readers use the caller's transaction session. This organization change preserves that lifecycle. The grant application service owns its write transaction, while bootstrap opens and closes its request-local session. Static `ProjectUseOnlyGrantMapper` conversions keep the route small and construct its typed response directly. `TransactionManager`, `ProjectGrantAuthorizer`, `OperationIdempotency` and `ProjectMembershipRepository` name its operational responsibilities. Follow the [implemented grant chain](../../docs/development/application-structure.md#grant-command-flow) and [ADR-0065](../../docs/adr/ADR-0065-application-services-own-write-transactions.md) for the real example. [ADR-0068](../../docs/adr/ADR-0068-model-project-grants-through-project-membership-aggregates.md) adds the persistence boundary: load Bob's existing membership, invoke `assign_use_only_grant()` and save supported additions through the specific repository. The membership protects its direct grant collection, while authorization retains eligibility/delegation rules. Infrastructure owns transaction-bound snapshots, the conditional project revision update and atomic audit. No membership provisioning, grant revocation or schema change is included.

`IdempotencyService` validates the reservation adapter's storage result and returns [distinct workflow outcomes](../../docs/development/jobs-and-idempotency.md#workflow-outcomes). The grant workflow returns completed synchronous metadata with a required expiry. The admission-only helper shares this retry decision while retaining its caller-owned transaction. These outcomes carry operation metadata and do not replace current authorization.

UUID identities remain runtime value objects. ORM columns remain UUIDs and enum columns perform real conversion. The immutable `Principal` holds account state; `AccessContextDTO` carries only its identity. The [data model](../../docs/development/data-model.md#implemented-principal-model) explains these distinctions.

Architecture and naming are reviewed manually. Unit tests mirror production roles; integration tests remain grouped by scenario. Automated checks cover behavior, typing, contracts, and integration outcomes.

---

## Configuration

`bootstrap/application_settings.py` aggregates `ApplicationSettings`. `KratosSettings`, `HydraSettings`, `CSRFSettings`, and `DatabaseSettings` live in their owners’ infrastructure `settings` packages; logging value definitions live in shared infrastructure `types`.

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

Application startup requires an absolute fingerprint-key path. `create_app()` reads the file and validates its 32-byte contents during construction, so a missing, unreadable, or malformed key prevents the backend from starting.

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

After cookie authentication, methods other than `GET`, `HEAD` and `OPTIONS` also need `X-Inframeld-CSRF: 1` and a matching `Origin` header. Human bearer writes do not need those browser headers. This is Inframeld's HTTP protection; Kratos checks its own CSRF values during browser account flows. The [Access guide](../../docs/development/access-control.md#implemented-human-authentication) describes the implemented boundary and its test coverage.

The web scaffold currently runs on `localhost:3000`, while these backend and Kratos examples use `127.0.0.1`. Browser integration still needs a consistent hostname and routing so the Kratos cookie reaches the backend. The trusted-origin list alone does not configure that routing.

Do not commit `.env` or `.env.test`.

The development passwords and Kratos secrets are only for local Compose and must not be reused in production. Kratos settings remain optional at startup. A request with no supported credential returns 401. A supplied cookie returns 503 when Kratos verification is not configured. A human bearer similarly returns 503 when Hydra verification is not configured. Malformed or competing credentials are rejected before reaching either verifier.

### Human bearer configuration

Alice's token and browser cookie must resolve to the same local account. The backend has verification adapters for both paths. The integration stack runs real Kratos and Hydra services to test that boundary. The development stack and complete first-party CLI login flow still need Hydra integration.

The standalone `HydraHumanOAuthCredentialRevoker` can invalidate one consent request's token chains or remove one remembered login through the private SDK. Callers supply typed target IDs and an explicit deadline after verifying ownership and installation binding. It makes one attempt and reports confirmed, failed or uncertain cleanup. [Real-provider tests](tests/integration/access/test_hydra_credential_cleanup.py) qualify the targeted behavior, refresh denial and preservation of other/later logins. Target inventory, durable retries, production callback/bootstrap wiring and recovery-block release remain separate work. See [the Access evidence](../../docs/development/access-control.md#hydra-cleanup-evidence).

When configuring the backend for a separately provisioned identity runtime, these are the supported settings:

| Environment variable | Meaning |
| --- | --- |
| `INFRAMELD_KRATOS__ADMIN_URL` | Explicit private Kratos identity API endpoint, required when Hydra is configured. |
| `INFRAMELD_HYDRA__ADMIN_URL` | Private Hydra endpoint used for token introspection. |
| `INFRAMELD_HYDRA__ISSUER` | Exact trusted Hydra issuer identifier. Do not derive it from an incoming token. |
| `INFRAMELD_HYDRA__API_AUDIENCE` | Exact API audience the token must contain. |
| `INFRAMELD_HYDRA__CLIENT_ID` | Fixed supported client `inframeld-cli`, also the default. |
| `INFRAMELD_HYDRA__REQUIRED_SCOPE` | Fixed supported scope `inframeld:api`, also the default. |

`ApplicationSettings` rejects Hydra configuration unless Kratos and its admin URL are also present. Choose endpoints and issuer/audience identifiers for the actual installation. Keep admin APIs private, including during development. These settings neither provision Hydra nor register the CLI client. [The deployment guide](../../docs/development/deployment.md#identity-runtime) owns those runtime requirements.

Both cookie and bearer authentication use deployment-configurable limits: `INFRAMELD_HUMAN_AUTHENTICATION__PROVIDER_TIMEOUT_SECONDS` defaults to five seconds and `INFRAMELD_HUMAN_AUTHENTICATION__TOTAL_TIMEOUT_SECONDS` defaults to ten. The total covers provider verification and the local principal lookup. A provider receives only the time still available within that total. See [the authentication budget contract](../../docs/development/access-contracts.md#session-checks) for timeout behavior and the remaining CLI request limit.

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
./scripts/dev-compose.sh test-run
./scripts/dev-compose.sh test-services-down
```

`check` verifies that the development PostgreSQL service is accepting connections. The integration test runner uses separate test-only PostgreSQL, Kratos and Hydra services.

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

CI first builds the integration image with Docker Buildx and restores its layers from GitHub Actions cache. Pushes to `main` update the shared cache, while pull requests only read it. A missing cache triggers a normal build. Cache imports and uploads each have a two-minute timeout. Upload failures do not fail the image build. Both Docker actions are pinned to verified release commit SHAs. This follows [Docker's GitHub Actions cache guidance](https://docs.docker.com/build/cache/backends/gha/) and [GitHub's action-pinning guidance](https://docs.github.com/en/actions/reference/security/secure-use#using-third-party-actions).

Buildx loads the result as `localhost/inframeld-integration-tests:ci`. The integration step sets `INFRAMELD_INTEGRATION_IMAGE` to that exact tag, so the wrapper uses the loaded image and skips its usual local build. The selected image must already exist locally. Compose never pulls the runner image. Ordinary local runs leave this variable unset and build `localhost/inframeld-integration-tests:local` using the container engine's normal local cache.

The image contains the Python environment and dependencies. Source code and tests are mounted from the current checkout, so every run still executes the current tests. Changes to the Dockerfile, dependency definitions or resolved base images rebuild affected layers. No test results, database volumes or runtime secrets enter the build cache. The host-side uv download cache is separate.

**Verification, 2026-10-15:** local Podman runs passed all 118 integration tests through both the normal-build and prebuilt-image paths. The prebuilt run skipped rebuilding. Selecting a missing image returned a clear failure, and cleanup preserved named volumes without leaving test containers or networks. Workflow validation used actionlint 1.7.12. Actual Docker/GitHub cache transfers and time saved still need confirmation from CI logs after a main-branch run has populated the cache.

The [bearer session tests](tests/integration/access/test_human_bearer_session_postgres.py) and [bearer grant-write tests](tests/integration/access/test_human_bearer_grant_http_postgres.py) use real application services, HTTP routes and temporary PostgreSQL databases. `Mock*Verifier` classes supply provider results. These scenarios check current local suspension, missing admission, grant authority and replay denial, cookie CSRF, provider failure handling and absence of unintended writes. The separate [real Hydra scenarios](tests/integration/access/test_human_hydra_session.py) issue actual tokens and exercise both provider SDKs through the backend.

A fixture such as `linked_human` or `grant_seed` runs when its name appears in the test's parameters. It commits that test's local account or permission setup before the request. Each test receives a fresh database, so using the same synthetic token does not share admission or grants between tests. The [Access evidence section](../../docs/development/access-control.md#implemented-human-authentication) distinguishes these backend scenarios from real-provider qualification and records the developer-reported passing run.

`pnpm test:integration` builds one locked test image and starts one stack from `compose.test.yaml`. A non-root `integration-tests` container waits up to 60 seconds for the required services, runs the existing application migration command, then runs the entire integration directory in one pytest process. All three database/Kratos/Hydra integration flags are enabled there, so provider scenarios run in the same summary. The browser tests cover registration, password login, session expiry, logout, disabled identities, code recovery, OIDC login, and password-confirmed OIDC account linking. Matching email alone must not link an account. Compose runs each provider's database migration before starting that provider.

The test stack publishes no host ports. [Shared test endpoints](tests/support/integration_services.py) use `postgres:5432`, Kratos public/admin at `kratos:4433`/`4434`, expiry-only Kratos at `kratos-expiring:4433`, Hydra public/admin at `hydra:4444`/`4445`, Mailpit at `mailpit:8025` and mock OIDC at `mock-oidc:8080`. The expiry instance issues 15-second sessions and shares the isolated Kratos database with standard Kratos. Hydra has its own ephemeral database and role.

The runner mounts source and tests read-only, reads the committed `.env.test.example` as its test configuration, and overrides endpoints and database credentials explicitly. It creates a temporary fingerprint key inside the container. Your host `.env.test`, development secrets and development database are not used by this command. Fast host-side checks still use the usual local test configuration and skip service-dependent scenarios.

Before startup and on exit, the wrapper removes only containers and networks labelled for the `inframeld-test` project, including leftovers from older test profiles. It verifies removal and reports cleanup failure as a command failure. The named application and Kratos test volumes survive. Application scenarios create and remove separate temporary databases, while uniquely named Kratos test identities remain in the retained Kratos volume. Run one integration command at a time.

The wrapper gives its background commands no terminal input. These commands need no interactive answers, and inheriting terminal input can suspend Podman before the wrapper reaches cleanup. Ctrl+C still interrupts the run and triggers cleanup. Allow a few seconds for graceful shutdown after Ctrl+C, because pnpm can return before the shell finishes stopping services.

For a focused run or debugging, keep the same private network:

```bash
./scripts/dev-compose.sh test-services-up
./scripts/dev-compose.sh test-run tests/integration/access/test_human_hydra_session.py
podman compose -p inframeld-test -f compose.test.yaml logs kratos hydra
./scripts/dev-compose.sh test-services-down
```

Use `docker compose` for logs when `INFRAMELD_CONTAINER_RUNTIME=docker` selects Docker. Each `test-run` performs readiness checks and migrations before pytest. The public wrapper accepts the same optional pytest arguments and handles cleanup automatically, for example `pnpm test:integration tests/integration/kratos`.

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
