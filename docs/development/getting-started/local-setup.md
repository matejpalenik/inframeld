# Run the backend locally

<a id="run-the-backend-locally"></a>

Start here to develop today’s FastAPI backend. The delivered development stack includes PostgreSQL, Kratos, Hydra and Mailpit, plus opt-in application and identity-recovery workers. The accepted vector and artifact topology is broader than this local stack. These instructions do not claim that the full CLI product is delivered.

<a id="quick-start"></a>

## Quick start

For normal local development, run the databases, Kratos, Hydra and Mailpit in Compose and the backend directly on your host.

From a clean checkout, install the committed dependencies from the repository root:

```bash
pnpm install --frozen-lockfile
uv sync --project apps/backend --locked
```

Use the Node and pnpm versions in the root `package.json` and the Python version in `apps/backend/.python-version`. CI's tool versions are pinned in `.github/workflows/ci.yml`.

Linux CI jobs explicitly use `ubuntu-26.04`, including backend, Quality, CodeQL and SDK qualification. CI installs its pinned Python version with the pinned uv tool before provisioning test keys. This avoids requiring an Ubuntu-specific build from GitHub's Python setup action. SDK macOS qualification remains a separate matrix target. Changing the CI host does not change the container base images or the product's supported operating systems.

<a id="1-create-your-local-environment"></a>

### 1. Create your local environment

On your first setup, copy the example environment file:

```bash
cp apps/backend/.env.example apps/backend/.env
```

Keep your existing `.env` on subsequent setups.

Provider-container settings belong in a separate repository-root `.env`, based on the root `.env.example`. Copy that example only if you do not already have a root `.env`. It controls native lifetimes and optional account-UI URLs. It is different from `apps/backend/.env`, which configures the host API. Keep both files ignored.

Create the separate backend test configuration before running checks:

```bash
cp apps/backend/.env.test.example apps/backend/.env.test
```

Keep `.env.test` in the ignored local configuration. It is not committed.

[Create the idempotency fingerprint key](#idempotency-fingerprint-key) and set its absolute path in both local environment files before running migrations or starting the backend.

<a id="2-start-postgresql-kratos-and-mailpit"></a>

### 2. Start the development dependencies

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

Application, Kratos and Hydra databases use three separate named volumes, preserved when containers stop. Kratos's public endpoint is at http://127.0.0.1:14434, Hydra's at http://127.0.0.1:14444 and Mailpit's inbox at http://127.0.0.1:18024. Provider administration stays private. The host API workflow supports browser authentication without publishing administration ports.

<a id="ordinary-application-worker"></a>

## Run the ordinary application worker

After explicitly applying the [current required schema revision](../../../apps/backend/src/inframeld_backend/shared/infrastructure/migrations/migration_runner.py) through [migrations](#migrations), start the worker from the same checkout as the API, with the development database still running:

```bash
mise exec -- uv run --project apps/backend --locked --env-file apps/backend/.env python -m inframeld_backend.application_worker
```

This explicitly loads the ignored API environment file for database settings. Worker startup checks the schema and existing installation identity without migrating. Look for `application_worker_ready`, then use Ctrl-C to stop the foreground process when finished. The worker has no HTTP listener and does not require the API's fingerprint key or provider credentials.

The production registry contains only the artifact cleanup and Project deletion handlers. [The operator guide](../operations/application-jobs.md) covers the opt-in `jobs` Compose service, effective settings, queue events and restart or shutdown uncertainty. There is no generic job submission or inspection interface.

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

<a id="application-key-verification-profiles"></a>

### Application-key verification profiles

`ApplicationKeyAuthenticationSettings` defines separate incoming HTTP and MCP verification profiles. Configure it in the backend environment file or process environment with the prefix `INFRAMELD_APPLICATION_KEY_AUTHENTICATION__`:

| Setting | Default | Purpose |
| --- | --- | --- |
| `HTTP_AUDIENCE` | Unset | Exact resource identity accepted by the HTTP application-key adapter. |
| `MCP_AUDIENCE` | Unset | Exact canonical resource identity accepted by the MCP application-key adapter. |
| `TRANSPORT_PROFILE` | `https` | URL validation for both configured audiences. |
| `TOTAL_TIMEOUT_SECONDS` | `10.0` | Finite positive total budget for key verification and local admission. |

Both committed backend env examples contain optional commented settings. Leave an unused audience unset. An empty string is invalid configuration. The default transport requires HTTPS URLs without credentials, query or fragment. For managed local development, `managed-local` instead requires literal IPv4 loopback HTTP, such as `http://127.0.0.1:8000`. It does not accept `localhost` or HTTPS. Invalid supplied settings prevent startup.

Audience values remain exact strings, including paths and trailing slashes. A key must match the adapter's configured audience and allow that adapter, `http` or `mcp`. The two configured audiences may be equal or different. Neither is inferred from Hydra, discovery, a request header or the stored key. The issuance implementation snapshots the configured audience separately for each selected adapter, with MCP using its canonical resource. It retains one key and secret when both adapters are selected. Fresh issuance requires all selected profiles, while authorized original replay preserves its original safe result without rebinding. The registered issuance router, persisted bindings and native contract are defined in this checkout. Complete client and platform qualification remains separate from that implementation status.

[ApplicationKeyIssuanceSettings](../../../apps/backend/src/inframeld_backend/access/infrastructure/settings/application_key_issuance_settings.py) reads the optional `INFRAMELD_APPLICATION_KEY_ISSUANCE__DEFAULT_LIFETIME_SECONDS` and `INFRAMELD_APPLICATION_KEY_ISSUANCE__MAXIMUM_LIFETIME_SECONDS` settings. Defaults are 7776000 seconds (90 days) and 31536000 seconds (365 days). Both are positive whole seconds within the exact safe-integer range, and the default cannot exceed the configured maximum. The 365-day default maximum is configurable. A selected expiry that cannot fit the supported UTC timestamp range is rejected before durable issuance effects. These settings are independent of Kratos/Hydra lifetimes.

Omitting an audience permits startup, but a supported application credential at that adapter returns `503 dependency_unavailable` before database or provider I/O. Missing credentials and unsupported identity families still return 401, and malformed or competing credentials return 400 before authentication. Application-key authentication is assembled independently of Kratos and Hydra. Human-provider configuration does not supply its verification profile or an alternate verifier.

The [authentication error contract](../error-handling.md#authentication-contract) separates credential rejection from local ineligibility. The adapters, profile configuration and PostgreSQL local-admission/current-key reads are implemented. [Ordinary Project action facts](../../../apps/backend/src/inframeld_backend/access/infrastructure/readers/postgres_project_action_facts_reader.py) use the explicitly supplied profile and current persisted key/account state within the calling operation's transaction. HTTP metadata composition forwards the configured HTTP profile. An MCP consumer must likewise inject its trusted MCP profile into its authorizer. Initial authentication cannot supply a missing current-authorization profile. Configuration alone does not establish complete client, platform or production qualification. These settings alone issue no key. Eligible human callers use the registered issuance operation, while a mounted MCP transport remains separate delivery work.

### Provider credential encryption key

Enable model connection credential writes in the host-run API by provisioning a separate 32-byte key. Configure the file path and the expected SHA-256 of its original bytes. Generate the key once. Capture the identifier during trusted setup and retain it with the installation configuration. A 32-byte file with a different identifier is refused even before the first write.

From the repository root, run this once as the development account that runs the host API:

```bash
mise exec -- python - <<'PY'
import os
from hashlib import sha256
from pathlib import Path
from secrets import token_bytes

os.umask(0o077)
key_file = Path.home() / ".config/inframeld/secrets/provider_credential.key"
key_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
material = token_bytes(32)
with os.fdopen(descriptor, "wb") as output:
    output.write(material)
print(f"INFRAMELD_PROVIDER_CREDENTIAL__KEY_FILE={key_file}")
print(f"INFRAMELD_PROVIDER_CREDENTIAL__EXPECTED_KEY_ID={sha256(material).hexdigest()}")
PY
```

Copy those two settings to `apps/backend/.env`. The command prints the path and its identifier. The raw key stays in the private file. If the file already exists, use its original trusted identifier. Restore the same file and identifier from the protected installation set after loss. Keep the credential encryption key separate from the required idempotency fingerprint key.

The API reads the key for a new credential change. Dedicated metadata reads and completed same-key recovery can return safe metadata while the file is unavailable. For a separately configured containerized API, supply a private read-only mount readable by the API user and configure the file's path inside the container. Development Compose leaves this optional mount to the operator. The current application worker has no credential-resolution consumer. See [provider credential storage](../../../.agents/skills/inframeld-access-models/references/provider-credential-storage.md).

### Application-key revocation

The implementation registers `revokeApplicationKey` through the human-authenticated POST route described in [the user guide](../../../apps/docs/src/app/guides/application-accounts/page.mdx#revoke-one-application-key). It requires current exact Revoke authority and a reviewed Project Access revision, without issuance delegation or a selected application-key verification profile. It returns safe metadata only. Exact original-request replay preserves the historical result, and revocation affects new incoming key checks rather than automatically cancelling admitted work.

[Migration 0029](../../../apps/backend/migrations/versions/0029_application_key_revocation.py) follows `0028_application_key_issuance` and adds retained safe revocation originals. The implemented schema does not mean an existing installation has already upgraded. Apply the checkout's required schema explicitly through [the normal migration command](#migrations) before starting it. Startup never migrates. The selected generated clients cover the implemented route, while deployment qualification remains separate and [human qualification #358](https://github.com/matejpalenik/inframeld/issues/358) remains unready and Not run. Account retirement stays with #233; mounted MCP and full saved CLI remain separate consumers.

<a id="development-services"></a>

## Development services

The root `compose.dev.yaml` manages application PostgreSQL, Kratos, Hydra and Mailpit. Kratos uses the `kratos_dev` role and `inframeld_kratos_postgres_data` volume. Hydra uses the `hydra_dev` role and `inframeld_hydra_postgres_data` volume. Both are separate from application storage. Kratos's public API uses `127.0.0.1:14434` and Hydra's uses `127.0.0.1:14444`. Neither admin API is published. Mailpit's SMTP stays private, with its inbox UI at `127.0.0.1:18024`.

PostgreSQL is exposed to the host only at:

```text
127.0.0.1:15432
```

Inside Compose, PostgreSQL uses port `5432`, Kratos public/admin use `http://kratos:4433`/`4434` and Hydra public/admin use `http://hydra:4444`/`4445`. The backend uses private verification endpoints while retaining the public Hydra issuer `http://127.0.0.1:14444/` and canonical API audience `http://127.0.0.1:8001`. Both host and container API use authority `kratos:local`. Provider migrations finish before their services start.

The development Kratos config enables password registration, login, and code-based recovery. Kratos sends development email to Mailpit. View captured messages at `http://127.0.0.1:18024`. The default HTTP graph retains placeholder self-service UI URLs. The separately delivered existing-human account pages use the [private HTTPS profile](../../../apps/web/README.md#https-reference-profile). Mailpit is for local development. An operator deployment needs its own SMTP configuration. Deployment-level OIDC sign-in is not configured by this Compose setup.

For company sign-in, use [optional identity integration](../guides/identity-integration.md). The default stack above does not configure an OIDC provider.

<a id="development-commands"></a>

### Development commands

Run these commands from the repository root:

```bash
pnpm dev:db               # Validate settings, migrate and start development dependencies
pnpm dev:db:reset         # Recreate the application database, preserving provider databases
pnpm dev:db:restart       # Restart PostgreSQL without removing its volume
pnpm dev:db:status        # Show development container status
pnpm dev:db:down          # Stop development containers, preserving all three database volumes

pnpm dev:compose           # Prepare providers and CLI registration, then start the API
pnpm dev:oauth:configure   # Explicitly reconcile the official CLI client
pnpm dev:compose:restart   # Restart existing services and reconcile registration before API
pnpm dev:compose:down      # Stop development containers, preserving database volumes
```

These commands use [`scripts/dev-compose.sh`](../../../scripts/dev-compose.sh), which automatically detects Podman Compose or Docker Compose.

Startup first builds the locked backend image and validates the four primary lifetime settings without provider I/O. It then starts databases, waits for readiness, runs provider migrations as completed setup steps and starts Kratos/Hydra. Database waits are bounded. Provider readiness runs inside the private Compose network using the same backend image, with at most 60 probes, two-second HTTP limits and one-second intervals. It does not depend on published host ports or inherited HTTP proxies. Setup failure stops the sequence. Explicit sequencing also avoids Podman restart problems with exited one-shot dependencies.

The script can also be run directly:

```bash
./scripts/dev-compose.sh up
./scripts/dev-compose.sh reset-db
./scripts/dev-compose.sh all
./scripts/dev-compose.sh configure-oauth
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
2. Keeps all three named volumes and drops and recreates only the `inframeld` database.
3. Starts the providers again with their existing identity and OAuth state.
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

Start the development dependencies, apply application migrations, and then start the backend container:

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

`pnpm dev:compose` prepares the providers, runs CLI client provisioning as a separate completed step, then starts the backend. API startup itself never creates or updates OAuth registrations. The image builder installs Git for the existing immutable SDK sources. Git is absent from the runtime image.

The backend binds inside the Compose network, with only its API port published to the host on the loopback interface.

<a id="configure-the-cli-client"></a>

### Configure the CLI client

Run the repeatable setup command after changing the managed client profile, trusted issuer or API audience:

```bash
pnpm dev:oauth:configure
```

It prepares the private services and runs `python -m inframeld_backend.provision_oauth_client` inside their network. The command reads focused Hydra configuration directly from environment variables, with no dotenv loading, application database or fingerprint key requirement. `--validate-only` checks configuration without contacting Hydra. Readiness has a 60-second total budget, followed by a 10-second provisioning budget. Both are configurable through `INFRAMELD_OAUTH_PROVISIONING__READINESS_TIMEOUT_SECONDS` and `INFRAMELD_OAUTH_PROVISIONING__TIMEOUT_SECONDS`.

Successful output identifies `inframeld-cli` and `created`, `updated` or `unchanged`. Exit 0 means the resulting profile was verified, 2 means invalid configuration/arguments and 1 means operational failure. Stopping and write admission share one synchronized decision. A stop that wins prevents mutation. Once a write is admitted, it may still be dispatched or finish late, and a timeout reports `outcome_unknown`. Do not infer failure or blindly repeat the mutation. After checking the provider, explicitly run setup again to reconcile current state. Diagnostics contain no client secrets or provider response bodies.

The provisioner registers the public S256-PKCE client with opaque access tokens and only `http://127.0.0.1/oauth/callback/<digest>` without a port. The existing setup command passes the exact `INFRAMELD_HYDRA__ISSUER` value, and `digest` is the full lowercase SHA-256 of its UTF-8 bytes. Preserve spelling, case, path and trailing slash. Do not normalize the issuer, choose a suffix or retain the shared callback path. Under the [accepted profile](../../../.agents/skills/inframeld-access-models/references/human-cli-login.md#cli-client-registration), only the ephemeral port varies during authorization, and exchange uses the identical complete redirect URI captured for that attempt. Client registration does not implement human login or acquire recipient proof.

[ADR-0125](../../adr/ADR-0125-bind-human-cli-callbacks-to-their-issuer.md) requires trusted private administration, no attacker-accessible registration or alternative approval path, and no registration of another issuer's callback on the honest server. Setup preserves unrelated clients, so reconciliation cannot certify those conditions. Setup patches the official client in place and reads back the managed profile. It does not delete/recreate the client or request a consent reset or revocation of independent login chains. During cutover, stop pending browser attempts and start new ones without rewriting their URI or retaining a shared-path fallback. The setup command does not cancel those attempts. Neither registration change nor code expiry proves outstanding consent/login flows have ended. The maintained pinned-Hydra scenarios passed legacy cutover and independent-chain preservation. Pre-cutover codes kept their original URI binding, while unchanged legacy consent was rejected without a code. These observations do not qualify human sign-in or proof acquisition. Setup's existing lifetime-override removal and bounded write/unknown-outcome rules remain unchanged.

Root `.env` can override these native settings:

```dotenv
TTL_ACCESS_TOKEN=5m
TTL_REFRESH_TOKEN=168h
TTL_AUTH_CODE=1m
SESSION_LIFESPAN=8h
```

They must be positive finite provider durations with ASCII digits, such as `30s` or `1h30m`, within the signed 64-bit nanosecond range. Unlimited, zero, negative, malformed, non-ASCII and overflowing values fail preflight. These exact effective values also reach provider startup. Other native timers and their pinned defaults are [listed separately](../../../.agents/skills/inframeld-access-models/references/human-cli-credential-lifecycle.md#provider-lifetime-configuration).

To apply provider environment changes, stop and recreate the stack with `pnpm dev:compose:down`, then `pnpm dev:compose`. Named volumes survive. Restarting an existing container or only reconciling the client does not load new environment values. Already issued credentials retain recorded deadlines. A shorter lifetime is not revocation.

Kratos uses its native private Hydra login integration. Set `SELFSERVICE_FLOWS_LOGIN_UI_URL` and `URLS_CONSENT` in root `.env` when the account pages are available. Until then, Kratos uses its existing UI placeholders and Hydra uses its native consent fallback. `/v1/oauth/consent` is a JSON API for a future page, not Hydra's browser-page URL. Provisioning does not make interactive login or the Rust CLI complete. Packaged runtime delivery remains #95.

The host API can keep its browser workflow. Bearer verification needs private Hydra and Kratos administration connectivity, supplied by the containerized API. Do not publish administration ports merely to enable host bearer development.

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

<a id="ordinary-project-creation"></a>

## Create an additional Project

An already admitted eligible human can read their own Organization access and create an ordinary Project through the public API. [Create an additional Project](../../../apps/docs/src/app/guides/create-project/page.mdx) explains the Organization ID/revision source, current `create-projects` permission, names, eighteen initial grants and original-request recovery. The new Project starts at Access revision `1` and metadata revision `0`, while its Organization Access revision stays unchanged.

This operation creates no starter or RAG resources and needs no host recipient proof. The CLI has no creation command. The guide assumes a current accepted human credential, with the complete supported account-to-API procedure and human acceptance still unfinished under [#313](https://github.com/matejpalenik/inframeld/issues/313). Private provider fixtures are engineering evidence, not a token-acquisition procedure.

<a id="project-metadata"></a>

## Project metadata and restricted repair

The backend supports metadata reads by permanent Project ID, exact Name resolution and atomic Name/Display-name changes for an existing Project. Changes require current human-only `edit-project-metadata` authority and a reviewed metadata revision. [Name and rename an existing Project](../../../apps/docs/src/app/guides/name-and-rename-project/page.mdx) gives the HTTP/generated-client path. It does not create Projects or allocate creator grants.

The backend-only maintenance command also consumes the narrow `repair-stranded-authority` request for that exact action. [Project metadata authority repair](../operations/project-metadata-repair.md) records its protected input, additional configuration and safe receipt/replay behavior. The [source-built transient proof example](../guides/recipient-proof.md) implements acquisition and direct protected-stdin handoff for an already-admitted recipient. Native combined and human qualification remain pending, so this is not a complete qualified first-grant walkthrough. `pnpm dev:oauth:configure` registers the client and does not acquire proof.

<a id="private-recovery-callbacks"></a>

## Private recovery callbacks

The development `recovery-callbacks` service uses the backend image on private port 8081. The `recovery` profile is opt-in. It shares the application database and expects the [current required schema revision](../../../apps/backend/src/inframeld_backend/shared/infrastructure/migrations/migration_runner.py), applied deliberately through the [ordinary migration command](#migrations) before startup. Starting the callback process never migrates a database.

Supply a dedicated 32 to 256 byte printable ASCII key through `INFRAMELD_RECOVERY_KEY_HOST_FILE`. The mounted regular file must be readable by the container's runtime UID 10001, with mode 0400 or 0600 as seen inside the container. Compose file-backed secrets do not reliably remap host ownership. Provision the correct runtime ownership rather than making the file group/world-readable. Do not reuse an API, database or fingerprint secret.

Run one recovery worker. When upgrading from a binary without the shared claim guard, stop the old worker and confirm it has exited before starting the replacement. Both cleanup families share one live local attempt. An earlier remote call can still finish after its lease expires. See [runtime and networking](../operations/runtime-and-networking.md#operate-the-runtime-and-its-network-boundaries).

After configuration, explicitly start both processes with `podman compose -f compose.dev.yaml --profile recovery up -d --no-deps recovery-callbacks recovery-worker` (use `docker compose` on Docker). This assumes the development database, Kratos and Hydra already run and the application database has been migrated. There is no host-port publication. The process needs `INFRAMELD_DATABASE__*` and `INFRAMELD_RECOVERY__*`, without Hydra or fingerprint configuration.

[The hook overlay example](../../../config/kratos/recovery-hooks.example.yaml) points directly to the private service. Render it into operator-owned protected Kratos configuration, replacing the placeholder with the same dedicated key and merging any existing provider overlay. Never commit that rendered file. Kratos must load both its normal configuration and this overlay. The three Jsonnet templates in `config/kratos/` emit identifiers only. The settings and password-saved templates intentionally repeat their source guards because Kratos forbids Jsonnet imports. Keep both files self-contained and validate both hooks after edits. Keep native hook activation explicit and start callbacks plus the recovery worker together. The worker uses the same backend image without a listener. Configure database settings, `INFRAMELD_RECOVERY_CLEANUP__AUTHORITY` and the private `INFRAMELD_RECOVERY_CLEANUP__HYDRA_ADMIN_URL`. The `INFRAMELD_RECOVERY_CLEANUP__KRATOS_ADMIN_URL` setting is optional for routine recovery alone and required to execute suspension cleanup. Development Compose supplies the worker's private `http://kratos:4434` endpoint. Keep both provider administration endpoints private. Its database pool defaults in Compose to two connections with no overflow. Neither process runs migrations. Exhausted or permanently rejected cleanup keeps access blocked. Use the protected host procedure for [routine recovery](#resume-recovery-cleanup) or the [original suspension](#inspect-or-continue-suspension-cleanup).

For rotation, configure a current file plus optional retiring file and `INFRAMELD_RECOVERY__RETIRING_KEY_ACCEPT_UNTIL` with an explicit timezone. The instantiated file reader loads protected keys at process construction. Restart the callback process to load changed files. Update Kratos to send the current key, then remove the retiring configuration after overlap. No product cookie or bearer token substitutes for the hook key. See [the private contract](../../../.agents/skills/inframeld-access-models/references/private-recovery-handoff.md#recovery-wire).

<a id="resume-recovery-cleanup"></a>

## Resume recovery cleanup from the host

Alice remains blocked after Hydra rejects cleanup or a run exhausts its budget. Fix the provider/configuration problem first. A trusted deployment operator can then authorize one additional twelve-attempt, one-hour run of the original recovery. This is a local container command with no network endpoint. Keep container-exec and database credentials restricted to operators.

Apply the [current required schema revision](../../../apps/backend/src/inframeld_backend/shared/infrastructure/migrations/migration_runner.py) deliberately through [migrations](#migrations) before starting the updated backend, callbacks or worker. Migration `0008_host_maintenance_receipts` introduced the maintenance receipt. The command never migrates a database. It needs only `INFRAMELD_DATABASE__*` and optional logging settings. The backend image installs both `inframeld-maintenance` and `python -m inframeld_backend.maintenance`, running as the existing non-root user.

Obtain the expected installation UUID from your protected installation record and the original recovery operation ID from protected recovery records. Replace the placeholders below. Choose a unique operator request ID and retain the exact request privately until its outcome is known. Supply attribution and the repair reason, without passwords, cookies or tokens.

```sh
podman compose -f compose.dev.yaml exec -T backend inframeld-maintenance <<'JSON'
{
  "schemaVersion": 1,
  "mode": "resume-recovery-cleanup",
  "expectedInstallationId": "<installation-uuid>",
  "operationId": "<unique-operator-request-id>",
  "recoveryOperationId": "<original-recovery-operation-id>",
  "operatorLabel": "Deployment operator",
  "reason": "Corrected Hydra administration configuration"
}
JSON
```

Use `docker compose` on Docker. Do not add a root/privileged override or expose Hydra administration. The separate [Project metadata repair mode](../operations/project-metadata-repair.md) requires additional identity-verification configuration and fresh recipient proof. It does not widen this recovery-continuation procedure.

Exit 0 returns the original accepted result: `cleanup-authorized` includes its run ID and UTC deadline, while `already-completed` and `cleanup-confirmed` create no provider run. Exit 2 means invalid input/configuration. Exit 1 means an operational failure or controlled rejection, with a safe code. `cleanup_run_active` means the existing budget still owns the work, including a live final attempt. A missing or interrupted stdout response is unknown. Send the **same exact request and request ID** to recover its original result. A new ID authorizes new work and is not a substitute for recovering a lost acknowledgment.

One immutable receipt retains both replay meaning and operator audit history. The command preserves prior runs, consumed attempts and confirmed steps. It neither calls Hydra nor releases access. The existing recovery worker executes unfinished work and applies normal proof-backed completion. See [the complete maintenance contract](../../../.agents/skills/inframeld-access-models/references/host-maintenance.md#recovery-cleanup-continuation).

<a id="inspect-or-continue-suspension-cleanup"></a>

## Inspect or continue the original suspension cleanup

A successful [suspension](../../../apps/docs/src/app/guides/admit-human/page.mdx#suspend-or-deliberately-restore-an-admitted-human) returns `202`, blocks product access and records the original cleanup obligation. Give the operator its `cleanupOperationId`. The receipt's separate `operationId` identifies the public request. Use the original cleanup ID for both maintenance intents.

Use a verified operator host with container-exec authority for the exact installation. Obtain its expected UUID from the protected installation record. Apply [the current required database revision](../../../apps/backend/src/inframeld_backend/shared/infrastructure/migrations/migration_runner.py) deliberately before starting the backend and worker. [Migration `0034_human_lifecycle`](../../../apps/backend/migrations/versions/0034_human_lifecycle.py) introduces these records.

The installed backend command reads one version 1 JSON object of at most 64 KiB through protected stdin. This mode uses the database and existing process settings. Put no provider endpoint, identity subject, product credential, password or token in the request. The recovery worker owns provider calls.

Create `inspect.json` in an operator-only directory with file mode `0600`. Replace the example IDs with the verified installation UUID, an operator correlation ID and the saved cleanup ID.

```json
{
  "schemaVersion": 1,
  "mode": "human-suspension-cleanup",
  "intent": "inspect",
  "expectedInstallationId": "00000000-0000-4000-8000-000000000001",
  "operationId": "incident-42-inspect",
  "cleanupOperationId": "00000000-0000-4000-8000-000000000002"
}
```

From the repository root, set `SUSPENSION_REQUEST_DIR` to that directory's absolute path. Use `docker compose` on Docker.

```sh
podman compose -f compose.dev.yaml exec -T backend inframeld-maintenance \
  < "$SUSPENSION_REQUEST_DIR/inspect.json"
```

Inspection saves no operator receipt. Read `execution` and the three states under `steps`. While work is `queued` or `running`, inspect again for progress. A running step can report `uncertain` while its dispatch lacks a saved outcome. For example, `stopped` with `kratosSessions: confirmed`, `hydraCliGrants: uncertain` and `hydraRememberedLogins: pending` means the worker saved the first confirmation, stopped with the second outcome unknown and left the third pending. The account stays blocked. Exhausted work is available for inspection.

For an eligible stopped original, resolve the cause before deciding whether to authorize continued work. If a step is uncertain, review the risk that the prior call may have taken effect. A continuation can authorize one repeat of that exact unresolved step. It keeps the original 24-hour queue deadline, the work deadline set on first claim and the maximum of three total attempts. Confirmed steps stay confirmed.

Create a protected `continue.json` in the same directory. Use the same installation and cleanup IDs, a unique operator request ID, and your own attribution and reason. Save the exact file before sending it.

```json
{
  "schemaVersion": 1,
  "mode": "human-suspension-cleanup",
  "intent": "continue",
  "expectedInstallationId": "00000000-0000-4000-8000-000000000001",
  "operationId": "incident-42-continue-01",
  "cleanupOperationId": "00000000-0000-4000-8000-000000000002",
  "operatorLabel": "Deployment operator",
  "reason": "Reviewed the Hydra transport failure and approved the unresolved step"
}
```

```sh
podman compose -f compose.dev.yaml exec -T backend inframeld-maintenance \
  < "$SUSPENSION_REQUEST_DIR/continue.json"
```

Exit `0` returns the original `requeued`, `already-scheduled` or `already-complete` outcome. Exit `2` indicates invalid input or settings. Exit `1` can report a controlled rejection, such as `suspension_cleanup_not_continuable`. If output is lost, explicitly repeat the command with the same unchanged `continue.json` to recover the original authorization. If the original did not commit, the same request can take effect only while its current checks still pass. Changed meaning under the same ID conflicts. Use a separate inspection to read current progress.

Restoration is a separate authorized action after all three confirmations and a security review. See the [protected maintenance contract](../../../.agents/skills/inframeld-access-models/references/host-maintenance.md#suspension-cleanup-maintenance) for exact inputs, status and replay.

## Rust CLI development

The [CLI guide](../../../apps/cli/README.md) covers the pinned Rust toolchain, clap-based offline commands, generated SDK adapter, strict checks and build-only packaging. `cargo run --locked -p inframeld-cli -- --help` requires no running backend. Installing the executable does not start the managed runtime.
