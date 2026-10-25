# Run the backend locally

<a id="run-the-backend-locally"></a>

Start here to develop today’s FastAPI backend. The delivered development stack includes PostgreSQL, Kratos and Mailpit. The accepted worker, vector and artifact topology is broader than this local stack. These instructions do not claim that the full CLI product is delivered.

<a id="quick-start"></a>

## Quick start

For normal local development, run PostgreSQL, Kratos, and Mailpit in Compose and the backend directly on your host.

From a clean checkout, install the committed dependencies from the repository root:

```bash
pnpm install --frozen-lockfile
uv sync --project apps/backend --locked
```

Use the Node and pnpm versions in the root `package.json` and the Python version in `apps/backend/.python-version`. CI's tool versions are pinned in `.github/workflows/ci.yml`.

<a id="1-create-your-local-environment"></a>

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

Keep `.env.test` in the ignored local configuration. It is not committed.

[Create the idempotency fingerprint key](#idempotency-fingerprint-key) and set its absolute path in both local environment files before running migrations or starting the backend.

<a id="2-start-postgresql-kratos-and-mailpit"></a>

### 2. Start PostgreSQL, Kratos, and Mailpit

```bash
pnpm dev:db
```

<a id="3-run-migrations"></a>

### 3. Run migrations

```bash
pnpm --filter @inframeld/backend migrate
```

<a id="4-start-the-backend"></a>

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

<a id="environment-and-development-services"></a>

## Environment and development services

`bootstrap/application_settings.py` aggregates `ApplicationSettings`. `KratosSettings`, `HydraSettings`, `CSRFSettings`, and `DatabaseSettings` live in their owners’ infrastructure `settings` packages. Logging value definitions live in shared infrastructure `types`.

Runtime configuration is loaded from files under `apps/backend`:

- `.env` , local development
- `.env.test` , used when `INFRAMELD_ENVIRONMENT=test`
- `INFRAMELD_TEST_ENV_FILE` , selects another test environment file. Relative paths are resolved from `apps/backend`
- `INFRAMELD_*` environment variables , override values loaded from dotenv files
- `.env.example` , documents local development database, Kratos, CSRF, and fingerprint-key path settings and may be copied to `.env`
- `.env.test.example` , documents isolated integration-test database, Kratos defaults, and the fingerprint-key path and may be copied to `.env.test`

<a id="idempotency-fingerprint-key"></a>

### Idempotency fingerprint key

`RequestFingerprintService` uses a deployment HMAC key to calculate fingerprints for requests containing secrets. PostgreSQL stores the resulting fingerprints and idempotency reservations, not the HMAC key. Keep the key stable while those reservations are retained, and keep it separate from the provider-credential encryption key. See [Background jobs, retries, and competing changes](../../../.agents/skills/inframeld-application-contracts/references/idempotency-and-replay.md#fingerprint-secret-bearing-requests-without-exposing-the-secret) for the request rule.

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

Both commands print no key material and refuse to overwrite an existing file. If an earlier setup already has a fingerprint key, move that exact file to the new host path instead of generating another. Include the host-managed file in the installation's [protected backup set](../operations/backups.md#backup). Restore the same key on a replacement VM. Do not generate a new one on restart or after losing the file.

Set the absolute host path in both `apps/backend/.env` and `apps/backend/.env.test`. The checked-in examples show the Linux VM path:

```dotenv
INFRAMELD_REQUEST_FINGERPRINT__KEY_FILE=/etc/inframeld/secrets/idempotency_fingerprint_hmac.key
```

On macOS, use the absolute path under your home directory instead. For the Compose backend, also set `INFRAMELD_FINGERPRINT_KEY_HOST_FILE` in the repository-root `.env` file to that same host path. [Podman Machine](https://docs.podman.io/en/latest/markdown/podman-machine-init.1.html) shares the home directory by default. It does not automatically share macOS `/etc`.

Only paths go in the environment files. For `pnpm dev:compose`, `compose.dev.yaml` defaults to the Linux VM's `/etc/inframeld/secrets` host file. The root `.env` value overrides that source on macOS. Compose mounts the selected file read-only as `/run/secrets/idempotency_fingerprint_hmac` and sets that container path automatically. The host-run backend and the container's UID 10001 must each be able to read the file when they run. [File-backed Compose secrets](https://docs.docker.com/reference/compose-file/services/#secrets) keep host ownership and permission bits. Grant the required runtime identities read access through restricted ownership, group membership, or ACLs. Do not make the key world-readable. Use a separate key for a separate installation, including an isolated test deployment.

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

`INFRAMELD_CSRF__TRUSTED_ORIGINS` is a JSON array of exact browser origins: scheme, host, and optional port, without a path. The host-run example permits requests originating from `http://127.0.0.1:8000`. `compose.dev.yaml` uses `http://127.0.0.1:8001`, its published backend port. An omitted or empty list denies cookie-authenticated writes.

After cookie authentication, methods other than `GET`, `HEAD` and `OPTIONS` also need `X-Inframeld-CSRF: 1` and a matching `Origin` header. Human bearer writes do not need those browser headers. This is Inframeld's HTTP protection. Kratos checks its own CSRF values during browser account flows. The [Access guide](../../../.agents/skills/inframeld-access-models/references/credential-dispatch.md#implemented-human-authentication) describes the implemented boundary and its test coverage.

The web scaffold currently runs on `localhost:3000`, while these backend and Kratos examples use `127.0.0.1`. Browser integration still needs a consistent hostname and routing so the Kratos cookie reaches the backend. The trusted-origin list alone does not configure that routing.

Do not commit `.env` or `.env.test`.

The development passwords and Kratos secrets are only for local Compose and must not be reused in production. Kratos settings remain optional at startup. A request with no supported credential returns 401. A supplied cookie returns 503 when Kratos verification is not configured. A human bearer similarly returns 503 when Hydra verification is not configured. Malformed or competing credentials are rejected before reaching either verifier.

<a id="development-services"></a>

## Development services

The application PostgreSQL, Kratos, and Mailpit services are managed by the root `compose.dev.yaml`. Kratos uses its own PostgreSQL service, `kratos_dev` database role, and `inframeld_kratos_postgres_data` volume, separate from the application database. Its public API is available on `127.0.0.1:14434`. Its admin API stays inside the Compose network. Mailpit's SMTP port stays inside that network, while its inbox UI is exposed only on the host loopback interface at `127.0.0.1:18024`.

PostgreSQL is exposed to the host only at:

```text
127.0.0.1:15432
```

Inside the Compose network, PostgreSQL listens on its standard port `5432` and Kratos's public API listens at `http://kratos:4433`. A host-run backend uses the public URL from `.env`. The backend Compose service overrides that URL with the internal address. Both use the `kratos:local` identity authority. The Kratos migration runs before the service starts.

The development Kratos config enables password registration, login, and code-based recovery. Kratos sends development email to Mailpit. View captured messages at `http://127.0.0.1:18024`. Its self-service UI URLs are placeholders until browser pages are implemented. Mailpit is for local development. An operator deployment needs its own SMTP configuration. Deployment-level OIDC sign-in is not configured by this Compose setup.

For company sign-in, use [optional identity integration](../guides/identity-integration.md). The default stack above does not configure an OIDC provider.

<a id="development-commands"></a>

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

These commands use [`scripts/dev-compose.sh`](../../../scripts/dev-compose.sh), which automatically detects Podman Compose or Docker Compose.

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

<a id="resetting-the-application-database"></a>

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

<a id="running-the-backend-in-compose"></a>

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

<a id="migrations"></a>

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

Use that documented migration command for operator execution.

Do not invoke Alembic directly for normal operation. Direct Alembic CLI invocations bypass the application's reporting boundary.

SQLAlchemy parameter hiding provides additional protection, but does not sanitize arbitrary database-driver messages.

Integration tests run the migration command automatically against `.env.test` before executing.

Do not add migrations to `pnpm dev` or API startup.

Read [testing](../guides/testing.md) next. For accepted production boundaries, see [runtime and networking](../operations/runtime-and-networking.md).
