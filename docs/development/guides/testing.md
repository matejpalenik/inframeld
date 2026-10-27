# Test one behavior, then its integration

<a id="test-one-behavior-then-its-integration"></a>

Alice changes grant handling. A focused behavioral test explains the rejected or successful outcome first. Integration tests then check the real database or provider boundary. Passing one layer does not qualify every product journey.

<a id="checks"></a>

## Checks

Run backend checks from the repository root:

```bash
pnpm check:backend
pnpm test:integration
```

`pnpm check:backend` runs backend formatting, linting, type checking, fast tests, and OpenAPI contract validation without PostgreSQL. It uses only the backend's locked Python environment and does not generate or install a Studio SDK.

<a id="unit-and-contract-tests"></a>

### Unit and contract tests

`pnpm check:backend` keeps service-dependent integration tests skipped. Unit directories mirror production capabilities. Strict Pyright also requires explicit `@override`. Unit, health, and OpenAPI checks run without PostgreSQL.

<a id="integration-tests"></a>

### Integration tests

CI runs the same `pnpm test:integration` command. There is no separate database-only CI suite.

CI first builds the integration image with Docker Buildx and restores its layers from GitHub Actions cache. Pushes to `main` update the shared cache, while pull requests only read it. A missing cache triggers a normal build. Cache imports and uploads each have a two-minute timeout. Upload failures do not fail the image build. Both Docker actions are pinned to verified release commit SHAs. This follows [Docker's GitHub Actions cache guidance](https://docs.docker.com/build/cache/backends/gha/) and [GitHub's action-pinning guidance](https://docs.github.com/en/actions/reference/security/secure-use#using-third-party-actions).

Buildx loads the result as `localhost/inframeld-integration-tests:ci`. The integration step sets `INFRAMELD_INTEGRATION_IMAGE` to that exact tag, so the wrapper uses the loaded image and skips its usual local build. The selected image must already exist locally. Compose never pulls the runner image. Ordinary local runs leave this variable unset and build `localhost/inframeld-integration-tests:local` using the container engine's normal local cache.

The image contains the Python environment and dependencies. Source code and tests are mounted from the current checkout, so every run still executes the current tests. Changes to the Dockerfile, dependency definitions or resolved base images rebuild affected layers. No test results, database volumes or runtime secrets enter the build cache. The host-side uv download cache is separate.

The [bearer session tests](../../../apps/backend/tests/integration/access/test_human_bearer_session_postgres.py) and [bearer grant-write tests](../../../apps/backend/tests/integration/access/test_human_bearer_grant_http_postgres.py) use real application services, HTTP routes and temporary PostgreSQL databases. `Mock*Verifier` classes supply provider results. These scenarios check current local suspension, missing admission, grant authority and replay denial, cookie CSRF, provider failure handling and absence of unintended writes. The separate [real Hydra scenarios](../../../apps/backend/tests/integration/access/test_human_hydra_session.py) issue actual tokens and exercise both provider SDKs through the backend.

A fixture such as `linked_human` or `grant_seed` runs when its name appears in the test's parameters. It commits that test's local account or permission setup before the request. Each test receives a fresh database, so using the same synthetic token does not share admission or grants between tests. The [Access evidence section](../../../.agents/skills/inframeld-access-models/references/credential-dispatch.md#implemented-human-authentication) distinguishes these backend scenarios from real-provider qualification and records the developer-reported passing run.

`pnpm test:integration` builds one locked test image and starts one stack from `compose.test.yaml`. A non-root `integration-tests` container waits up to 60 seconds for the required services, runs the existing application migration command, then runs the entire integration directory in one pytest process. All three database/Kratos/Hydra integration flags are enabled there, so provider scenarios run in the same summary. The browser tests cover registration, password login, session expiry, logout, disabled identities, code recovery, OIDC login, and password-confirmed OIDC account linking. Matching email alone must not link an account. Compose runs each provider's database migration before starting that provider.

The test stack publishes no host ports. [Shared test endpoints](../../../apps/backend/tests/support/integration_services.py) use `postgres:5432`, Kratos public/admin at `kratos:4433`/`4434`, expiry-only Kratos at `kratos-expiring:4433`, Hydra public/admin at `hydra:4444`/`4445`, Mailpit at `mailpit:8025` and mock OIDC at `mock-oidc:8080`. Standard Kratos uses eight-hour sessions. The expiry instance retains 15-second sessions and shares the isolated Kratos database. Hydra has its own ephemeral database and role.

The same graph includes `hydra-lifetimes:4444`/`4445` with a separate tmpfs database, access/refresh lifetimes of 30/120 seconds and a five-second code lifetime. [Provisioning scenarios](../../../apps/backend/tests/integration/access/test_hydra_cli_provisioning.py) run the production client provisioner and compare actual issued/introspected deadlines and expired-code exchange with the default provider. This remains one collection, without host ports or a container socket in the runner.

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

Qualify development OAuth setup separately without using existing developer databases:

```bash
bash scripts/test-dev-oauth.sh
```

This renders the development graph into a unique temporary project, removes published ports, assigns isolated volumes and supplies a temporary test-only key. It calls the real `dev-compose.sh` operations for dependency startup, API startup, explicit provisioning and restart. The qualification script prepares only the disposable application migration and observations, without copying the startup sequence. It checks API health, repeat provisioning and persisted registration after restart. Cleanup removes only that project's containers, network, volumes and unique image. The usual development volumes remain untouched. Select Docker with `INFRAMELD_CONTAINER_RUNTIME=docker` where available. A local Podman result does not establish Docker CI execution.

The isolated check supplies `INFRAMELD_DEV_COMPOSE_FILE` and `INFRAMELD_DEV_COMPOSE_PROJECT` together. The file must be an existing absolute path. Missing, empty or incomplete overrides fail before container commands run. Normal development keeps the default Compose selection, and integration commands keep the fixed `inframeld-test` project. Provider readiness uses private service addresses, so the same startup path works without published ports.

---

For scaffold-first TDD, protocol doubles and meaningful tests, read [Testing and documentation](../../../.agents/skills/inframeld-coding-standards/references/testing-and-documentation.md). Architecture, import-boundary, naming and composition enforcement tests remain prohibited. Review those conventions manually.

### Native recovery delivery

The private integration graph adds an ephemeral application database, a migration prerequisite, the real callback app and a separate `kratos-recovery` instance. Existing provider probes retain their configurations. No test service publishes a port.

[Native tests](../../../apps/backend/tests/integration/kratos/test_native_recovery_notifications.py) exercise source extraction, session association, password persistence, native revocation, rejected persistence and lost acknowledgments. Test-only forwarding gates delay or fail delivery to a fixed private target. They expose no production control routes and record only allowlisted identifiers. [PostgreSQL tests](../../../apps/backend/tests/integration/access/test_identity_recovery_notifications_postgres.py) cover coherent association observations, receipts, original budgets, rollback and concurrency. Application tests exercise association decisions before persistence and derive the initial budget from the stored receipt time. Later settings events must preserve the first job/run and confirmed progress. Middleware tests verify non-cacheable headers without buffering responses. Both self-contained Jsonnet templates are exercised through native hooks, including source recognition and session inheritance. These tests do not execute Hydra cleanup or release a block.

### Recovery execution qualification

The private integration graph has a separate `recovery-execution-postgres` database, callback process and native Kratos configuration. [Native worker tests](../../../apps/backend/tests/integration/access/test_native_recovery_cleanup_worker.py) start the real production worker command as a bounded subprocess inside the runner. This requires no Docker socket or production control endpoint, and leaves callback-only scenarios independent of cleanup. They cover provider unavailability, process replacement, original budgets, protected recovery sessions and old-version rejection after release.

[Execution tests](../../../apps/backend/tests/integration/access/test_identity_recovery_cleanup_execution_postgres.py) qualify claims and proof against fresh PostgreSQL databases. The [migration tests](../../../apps/backend/tests/integration/postgres/test_migrations_postgres.py) preserve the 0006 handoff while adding execution records. `scripts/test-dev-oauth.sh` also starts and restarts the dedicated worker through an isolated development project with no published ports. None of these commands should start or migrate an existing development database.

The private runner also waits for public signing keys from both Hydra instances. [Pinned Hydra generates missing signing keys lazily](https://github.com/ory/hydra/blob/v26.2.0/jwk/handler.go). Key setup has a thirty-second request limit within the existing sixty-second shared startup deadline. This keeps initial key generation outside the five-second OAuth request budgets without weakening their assertions. Worker-process helpers await child exit and log draining even when a scenario is cancelled during context exit.

### Protected maintenance qualification

The [PostgreSQL maintenance tests](../../../apps/backend/tests/integration/access/test_identity_recovery_cleanup_resume_postgres.py) exercise request replay, conflicting meaning, concurrent authorization, budgets, ownership fencing and atomic receipt/run persistence. Failed commits and lost acknowledgments after successful commits have separate cases. The [native worker scenario](../../../apps/backend/tests/integration/access/test_native_recovery_cleanup_worker.py) runs the installed command after a controlled provider rejection, then verifies real Hydra cleanup and original-checklist release through the worker.

`bash scripts/test-dev-oauth.sh` also runs both installed maintenance entry points in the production backend image as the non-root user, without `PYTHONPATH` or provider credentials. It uses its disposable installation and checks safe database-backed output. It does not start or migrate an existing developer database. Run the complete integration suite with `pnpm test:integration tests/integration --durations=20` to include slowest-test timings.
