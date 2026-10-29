# Test one behavior, then its integration

<a id="test-one-behavior-then-its-integration"></a>

Alice changes grant handling. A focused behavioral test explains the rejected or successful outcome first. Integration tests then check the real database or provider boundary. Passing one layer does not qualify every product journey.

The [Testing skill](../../../.agents/skills/inframeld-testing/SKILL.md) owns layer selection, dependency isolation and interpretation of evidence. [Coding Standards](../../../.agents/skills/inframeld-coding-standards/references/testing-and-documentation.md) retains shared TDD/documentation, while [Python Standards](../../../.agents/skills/inframeld-python-standards/SKILL.md) and [Rust Standards](../../../.agents/skills/inframeld-rust-standards/SKILL.md) retain language-specific test-code conventions. This runbook retains commands and detailed environment procedures. For cross-language client conformance, use the [SDK qualification reference](../../../.agents/skills/inframeld-sdks/references/shared-qualification.md). The unified SDK runner and operation-coverage gate are implemented. Automatic Linux checks cover applicable PRs, with macOS for generator and platform-sensitive process/browser/lifecycle changes, plus manual runs. Report actual platform execution separately, and configure external branch rules to require the SDK conformance aggregate.

<a id="checks"></a>

## Checks

Run backend checks from the repository root:

```bash
pnpm check:backend
pnpm test:integration
```

`pnpm check:backend` runs backend formatting, linting, type checking, fast tests, and OpenAPI contract validation without PostgreSQL. It uses only the backend's locked Python environment and does not generate or install a Studio SDK.

<a id="ci-selection"></a>

### CI selection and full verification

Alice changes the CLI README. CI still checks formatting and commit messages, but does not compile Rust or start identity providers. If her PR also contains an earlier Rust change, the complete PR diff still selects CLI checks at its latest head.

The [shared selector](../../../.github/scripts/ci_changes.py) owns dependency groups. The [reusable workflow](../../../.github/workflows/changes.yml) tests that selector, reads the complete Git comparison and publishes fixed check-family flags. All four caller workflows report selection even when their expensive work is not applicable. A selection summary records the original paths and selected families. It does not establish that application tests ran.

| Inputs | Selected checks |
| --- | --- |
| Authored Markdown/MDX, skills, README and AGENTS files outside consumed application content | Repository formatting and commit messages |
| Backend runtime, dependencies, migrations and shared test fixtures | Backend fast checks and integration. HTTP-affecting inputs also select SDK verification |
| Backend unit tests | Backend fast checks. Contract tests and designated SDK fixtures also select SDK verification |
| Integration Compose, provider configuration, runner scripts and image inputs | Backend fast checks and integration |
| Web implementation, assets and configuration | Web lint, types and build. Language inputs also select JavaScript/TypeScript CodeQL |
| Documentation app pages, navigation, assets and configuration | Documentation formatting, lint, types, content and link checks, tests and production build |
| Delivery helper implementation and configuration | Helper formatting, lint, strict types and behavioral tests, without product services |
| CLI implementation, xtask, build inputs, tests and Rust SDK | CLI fast checks and all four native targets. SDK inputs also select conformance |
| Cargo manifests, lockfile and Rust toolchain | Rust consumers and dependency audits. Audit-policy-only changes select the audit |
| SDK code, generators, tools, schemas, generated output and fixtures | Existing SDK conformance, including macOS for its platform-sensitive inputs |
| Shared pnpm manifests, lockfile and trust policy | Workspace consumers and SDK verification, without Cargo-only native packaging |
| Python or JavaScript/TypeScript source and dependency/analysis inputs | That CodeQL language across its complete existing analysis scope |
| A caller workflow | That workflow's checks |
| Shared selection code or an unclassified non-documentation input | Conservative full verification, with the reason in the summary |

Consumed fixture data, generated documentation and source-tree resources are evaluated before the prose exclusion. Do not make a global Markdown exclusion that hides those inputs. Keep dependency groups explicit instead of selecting individual tests or building a dependency graph.

Contributor prose in the web and documentation apps selects that app's formatting dependencies without selecting its application checks. Shared formatter configuration selects both apps' formatting dependencies. Repository Prettier checking excludes each unchanged app tree when its stylesheet dependencies are unnecessary. Quality always runs the small delivery helper behavioral suite. Delivery helper changes also select Ruff and strict type checks.

**Quality** owns repository formatting, commit validation and selected package fast checks/builds. It installs only those workspace packages and the Python/Rust toolchains they need. Backend fast checks include OpenAPI validation. **Backend foundation** waits for successful Quality when integration is selected, then builds the existing integration image, runs the complete private suite and verifies teardown. It does not repeat backend fast checks. Native CLI jobs retain strict checks, installation and repeated-build qualification on all four existing targets when selected. Their dependency audit is selected separately.

PRs compare merge-base to head, including every commit in the PR. Changes only on the base branch do not select that PR's work. Main pushes compare the event's before/after revisions. Git reports additions, deletions and both sides of a rename, without an API file-list cutoff. An absent initial baseline selects full verification. Failed comparisons and invalid outputs fail detection. Quality, Backend foundation and the SDK aggregate reject failed selection rather than treating it as a valid skip.

Scheduled CodeQL runs still scan both languages. The weekly CLI security run audits dependencies without starting native packaging, because advisories can change independently of source. Manual runs select complete verification for their workflow. The SDK's existing `macos` input remains available and defaults to `true`.

From the repository root, check the selector without application dependencies:

```bash
python3 -m unittest discover -s .github/scripts -p test_ci_changes.py
```

To inspect the selection for committed changes on your branch:

```bash
ci_selection_dir="$(mktemp -d)"
EVENT=pull_request BASE="$(git rev-parse main)" HEAD="$(git rev-parse HEAD)" \
  GITHUB_OUTPUT="$ci_selection_dir/outputs" \
  GITHUB_STEP_SUMMARY="$ci_selection_dir/summary.md" \
  python3 .github/scripts/ci_changes.py
cat "$ci_selection_dir/outputs"
```

Uncommitted edits do not participate in that Git comparison. The script writes only the two selected temporary report files. A manual full run of the published branch uses the existing workflows separately:

```bash
ci_branch=main
gh workflow run ci.yml --ref "$ci_branch"
gh workflow run cli.yml --ref "$ci_branch"
gh workflow run sdk-conformance.yml --ref "$ci_branch" -f macos=true
gh workflow run codeql.yml --ref "$ci_branch"
```

When adding a consumed configuration file, fixture or workspace member, update the selector and its behavioral examples together. Keep the source paths and reasons in one owner. Local developer commands such as `pnpm check` remain complete and unchanged.

**Merge and evidence boundaries.** Preserve the current required Quality, Backend foundation and CodeRabbit checks and the separate native CodeQL alert rule. Job-level selection avoids [missing required workflow checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks#handling-skipped-but-required-checks). Native [CodeQL merge protection](https://docs.github.com/en/code-security/concepts/code-scanning/merge-protection) must also accept documentation-only and single-language skips in published PRs. That remote compatibility remains pending until observed. If GitHub requires analysis in those cases, retain PR analysis as the compatibility exception. Do not replace native protection with a successful shell job, change alert thresholds or upload fabricated results. External activation of additional required checks remains a separate decision.

<a id="ci-dependency-caches"></a>

### CI dependency caches

Alice reruns a selected CLI check after changing a command. CI restores compatible third-party dependencies, compiles the current workspace crates and executes the tests again. A cache hit never substitutes for a check result.

| Owner | Reused inputs | Work that still runs |
| --- | --- | --- |
| Quality and native CLI jobs | Cargo downloads and compiled third-party dependencies | Selected formatting, lint, types, tests and builds. Native jobs also run rustdoc and both packaging/installation passes |
| CLI dependency audit | The exact pinned `cargo-deny` executable | Tool-version validation and both audits against current advisories, including weekly runs |
| SDK Rust jobs | Cargo dependencies and the content-addressed patched generator executable | Source/patch digest and tool-version checks, regeneration, fresh generator-library compilation/tests, native qualification and package consumers |
| Quality, Backend foundation and SDK jobs | The pnpm package store | Frozen installation and every selected command |
| SDK jobs | Original generator archives and uv dependency downloads/wheels | Archive verification, TypeScript/Python resource patching, Python SDK builds and fresh consumer environments |

The caller workflows own these caches. Rust caching uses the pinned [Rust cache action](https://github.com/Swatinem/rust-cache/tree/v2.9.3) with workspace-crate and Cargo-bin caching disabled. Its dependency pruning removes authored workspace artifacts and non-build outputs before saving. Job family, runner image, architecture, compiler, target, Cargo inputs and relevant workflow/build settings separate compatible caches. The root Cargo profile configuration and native packaging flags participate explicitly. The SDK generator cache also includes its manifest, actual patches and preparation code. Generator-library and temporary consumer compilation directories are not restored.

The audit executable has an exact version/platform/compiler key without fallback keys. A missing, unusable or incorrect version triggers locked installation. Advisory databases and audit verdicts are not cached. Original SDK archives are checked against their committed hashes on every use. Cache misses follow normal installation and build paths. Integrity failures still fail the check.

SDK jobs select their existing tool-cache override under `RUNNER_TEMP`. The uv action and SDK subprocesses use the same `uv` directory. Native Python typing uses the selected environment. The [SDK runbook](../../../packages/sdk-tools/README.md#ci-and-proof-boundaries) owns the qualification details.

Keep caches limited to these inputs. Do not cache test verdicts, generated SDK output, release/package archives, evidence, installed consumer environments, database volumes, provider state, certificates or credentials. CLI reproducibility still explicitly cleans the CLI package between its two builds. This permits dependency reuse and does not claim a clean rebuild of every third-party crate. Existing Docker layer caching below retains its separate main-only write policy.

To qualify a cache change, inspect its first published run and rerun the same revision. Confirm cache keys/hits, selected command execution and newly produced evidence on both runs. Compare restoration, saving, compilation and total durations. For a controlled cold run, remove only the relevant GitHub Actions cache entries before rerunning, with the repository owner's authorization. Cache misses are supported and need no workflow flag. If cache overhead exceeds its benefit, remove that cache. Local checks do not establish remote cache hits or speedups.

<a id="unit-and-contract-tests"></a>

### Unit and contract tests

`pnpm check:backend` keeps service-dependent integration tests skipped. Unit directories mirror production capabilities. Strict Pyright also requires explicit `@override`. Unit, health, and OpenAPI checks run without PostgreSQL.

<a id="integration-tests"></a>

### Integration tests

CI runs the same `pnpm test:integration` command when integration inputs change, after Quality succeeds. There is no separate database-only CI suite.

CI first builds the integration image with Docker Buildx and restores its layers from GitHub Actions cache. Pushes to `main` update the shared cache, while pull requests only read it. A missing cache triggers a normal build. Cache imports and uploads each have a two-minute timeout. Upload failures do not fail the image build. Both Docker actions are pinned to verified release commit SHAs. This follows [Docker's GitHub Actions cache guidance](https://docs.docker.com/build/cache/backends/gha/) and [GitHub's action-pinning guidance](https://docs.github.com/en/actions/reference/security/secure-use#using-third-party-actions).

Buildx loads the result as `localhost/inframeld-integration-tests:ci`. The integration step sets `INFRAMELD_INTEGRATION_IMAGE` to that exact tag, so the wrapper uses the loaded image and skips its usual local build. The selected image must already exist locally. Compose never pulls the runner image. Ordinary local runs leave this variable unset and build `localhost/inframeld-integration-tests:local` using the container engine's normal local cache.

The image contains the Python environment and dependencies. Source code and tests are mounted from the current checkout, so every run still executes the current tests. Changes to the Dockerfile, dependency definitions or resolved base images rebuild affected layers. No test results, database volumes or runtime secrets enter the build cache. The host-side uv download cache is separate.

The [bearer session tests](../../../apps/backend/tests/integration/access/test_human_bearer_session_postgres.py) and [bearer grant-write tests](../../../apps/backend/tests/integration/access/test_human_bearer_grant_http_postgres.py) use real application services, HTTP routes and temporary PostgreSQL databases. `Mock*Verifier` classes supply provider results. These scenarios check current local suspension, missing admission, grant authority and replay denial, cookie CSRF, provider failure handling and absence of unintended writes. The separate [real Hydra scenarios](../../../apps/backend/tests/integration/access/test_human_hydra_session.py) issue actual tokens and exercise both provider SDKs through the backend.

A fixture such as `linked_human` or `grant_seed` runs when its name appears in the test's parameters. It commits that test's local account or permission setup before the request. Each test receives a fresh database, so using the same synthetic token does not share admission or grants between tests. The [Access evidence section](../../../.agents/skills/inframeld-access-models/references/credential-dispatch.md#implemented-human-authentication) describes the implemented human-authentication boundary. This guide previously attributed a developer-reported passing run to that section, but the run record is absent there. Preserve that pass only as an unverified historical report, without treating the link as current execution evidence.

`pnpm test:integration` builds one locked test image and starts one stack from `compose.test.yaml`. A non-root `integration-tests` container waits up to 60 seconds for the required services, runs the existing application migration command, then runs the entire integration directory in one pytest process. All three database/Kratos/Hydra integration flags are enabled there, so provider scenarios run in the same summary. The browser tests cover registration, password login, session expiry, logout, disabled identities, code recovery, OIDC login, and password-confirmed OIDC account linking. Matching email alone must not link an account. Compose runs each provider's database migration before starting that provider.

The test stack publishes no host ports. [Shared test endpoints](../../../apps/backend/tests/support/integration_services.py) use `postgres:5432`, Kratos public/admin at `kratos:4433`/`4434`, expiry-only Kratos at `kratos-expiring:4433`, Hydra public/admin at `hydra:4444`/`4445`, Mailpit at `mailpit:8025` and mock OIDC at `mock-oidc:8080`. Standard Kratos uses eight-hour sessions. The expiry instance retains 15-second sessions and shares the isolated Kratos database. Hydra has its own ephemeral database and role.

Password-breach checks use the deterministic HTTPS fixture at `password-breaches:8443`, served by the same non-root integration image. Startup first runs a network-isolated TLS initializer that prepares volume ownership and drops to the fixture user before generating a fresh CA and a 24-hour server certificate. All test Kratos variants keep HIBP checking enabled, trust the generated CA and reject lookup network errors. The runner requires verified HTTPS readiness within its existing startup deadline. Registration, login and recovery do not depend on the public HIBP service. [Fixture TLS instructions](../../../apps/backend/tests/fixtures/password-breaches/README.md) own generation, permissions, expiry and cleanup. Teardown removes only the two explicitly named and labelled TLS volumes, preserving named database volumes. Repeated tests against a running stack reuse its certificates. Restart the stack after expiry. No host trust installation or CI secrets are required. The native breach tests prove ordinary-password acceptance, breached-password rejection without identity/session creation and rejection of the fixture certificate without explicit CA trust.

The Hydra test helper accepts `kratos_public_url` separately from its Hydra endpoints. Recovery-worker scenarios select `kratos-recovery-execution:4433` for cookie verification. Standard tests keep the default Kratos endpoint. Rejected cookie verification stops before OAuth authorization, without automatic login or another verification target.

The same graph includes `hydra-lifetimes:4444`/`4445` with a separate tmpfs database, access/refresh lifetimes of 30/120 seconds and a five-second code lifetime. [Provisioning scenarios](../../../apps/backend/tests/integration/access/test_hydra_cli_provisioning.py) run the production client provisioner and compare actual issued/introspected deadlines and expired-code exchange with the default provider. This remains one collection, without host ports or a container socket in the runner.

The runner mounts source and tests read-only, reads the committed `.env.test.example` as its test configuration, and overrides endpoints and database credentials explicitly. It creates a temporary fingerprint key inside the container. Your host `.env.test`, development secrets and development database are not used by this command. Fast host-side checks still use the usual local test configuration and skip service-dependent scenarios.

Before startup and on exit, the wrapper removes containers and networks labelled for the `inframeld-test` project, including leftovers from older test profiles, then removes only the two explicitly named and ownership-labelled TLS volumes. It verifies removal and reports cleanup failure as a command failure. The named application and Kratos database volumes survive. Application scenarios create and remove separate temporary databases, while uniquely named Kratos test identities remain in the retained Kratos volume. Run one local integration operation at a time. Overlapping commands are unsupported and no runtime lock enforces this convention.

The wrapper gives its background commands no terminal input. These commands need no interactive answers, and inheriting terminal input can suspend Podman before the wrapper reaches cleanup. Ctrl+C still interrupts the run and triggers cleanup. Allow a few seconds for graceful shutdown after Ctrl+C, because pnpm can return before the shell finishes stopping services.

For a focused run or debugging, keep the same private network:

```bash
./scripts/dev-compose.sh test-services-up
./scripts/dev-compose.sh test-run tests/integration/access/test_human_hydra_session.py
podman compose -p inframeld-test -f compose.test.yaml logs kratos hydra
./scripts/dev-compose.sh test-services-down
```

Use `docker compose` for logs when `INFRAMELD_CONTAINER_RUNTIME=docker` selects Docker. Each `test-run` performs readiness checks and migrations before pytest. The public wrapper accepts the same optional pytest arguments and handles cleanup automatically, for example `pnpm test:integration tests/integration/kratos`.

### Serial integration workflow

The Bash wrapper owns one automatic run from startup through teardown. Manual start, test and stop commands remain available for debugging, without reservations or worktree restrictions. Stop the current run before starting another local integration command. CI executes its integration steps sequentially on its job's isolated GitHub-hosted runner. No parallel pytest workers or shared-stack coordination are configured.

On INT or TERM, the wrapper terminates the active phase's process group before cleaning up the stack. It allows five seconds after TERM, then sends KILL if needed and allows five more seconds. It checks the whole group, including descendants whose leader has exited, and reaps the immediate child. Surviving processes are reported as failure. INT and TERM retain exit codes `130` and `143`. Existing nonzero failures survive cleanup errors, while cleanup failure after successful tests makes the command fail. If cleanup is interrupted, rerun `./scripts/dev-compose.sh test-services-down`.

Automatic teardown runs one cleanup attempt with a fixed 60-second work budget. It launches cleanup in a separate process group, then uses the same five-second TERM and five-second KILL grace periods if the work budget expires. Cleanup therefore has a maximum nominal duration of 70 seconds, excluding OS scheduling delays. The parent shields finalization from repeated signals, while the cleanup child restores default signal handling. The wrapper reports timeout as potentially incomplete cleanup and retains the manual recovery instruction. Killing the host CLI does not prove that the container engine finished removing remote resources. Direct manual `test-services-down` retains its existing behavior and does not use this automatic deadline. No public timeout flag or environment setting is provided.

The runner checks public certificate-expiry metadata before network readiness. Missing, invalid or expired metadata fails immediately with restart instructions. Otherwise the existing 60-second readiness deadline remains. Timeout diagnostics retain safe categories such as certificate verification, connection failure, request timeout or HTTP status. They never echo upstream response bodies or arbitrary exception messages. To renew credentials, run `test-services-down`, then `test-services-up`, then `test-run` with the original test arguments.

Fast wrapper tests exercise real controlled child processes and exit handling without containers. The complete application integration suite uses the actual private stack. Backend foundation CI additionally checks that teardown left no project containers, networks or TLS volumes and retained the two named database volumes. This check runs after successful or failed integration execution, except when the job was cancelled.

Qualify development OAuth setup separately without using existing developer databases:

```bash
bash scripts/test-dev-oauth.sh
```

This renders the development graph into a unique temporary project, removes published ports, assigns isolated volumes and supplies a temporary test-only key. It calls the real `dev-compose.sh` operations for dependency startup, API startup, explicit provisioning and restart. The qualification script prepares only the disposable application migration and observations, without copying the startup sequence. It checks API health, repeat provisioning and persisted registration after restart. Cleanup removes only that project's containers, network, volumes and unique image. The usual development volumes remain untouched. Select Docker with `INFRAMELD_CONTAINER_RUNTIME=docker` where available. A local Podman result does not establish Docker CI execution.

The isolated check supplies `INFRAMELD_DEV_COMPOSE_FILE` and `INFRAMELD_DEV_COMPOSE_PROJECT` together. The file must be an existing absolute path. Missing, empty or incomplete overrides fail before container commands run. Normal development keeps the default Compose selection, and integration commands keep the fixed `inframeld-test` project. Provider readiness uses private service addresses, so the same startup path works without published ports.

---

For scaffold-first TDD and meaningful documentation, read the [shared testing contract](../../../.agents/skills/inframeld-coding-standards/references/testing-and-documentation.md). Read [Python test conventions](../../../.agents/skills/inframeld-python-standards/references/testing-and-documentation.md) for backend protocol doubles and [Rust Standards](../../../.agents/skills/inframeld-rust-standards/SKILL.md) for Rust tests. Architecture, import-boundary, naming and composition enforcement tests remain prohibited. Review those conventions manually.

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

For SDK changes, the [tooling architecture](../../../packages/sdk-tools/docs/architecture.md) and [endpoint walkthrough](../../../packages/sdk-tools/docs/adding-endpoint.md) describe ordinary Node feature tests across all five native profiles. Complete `sdk:verify` includes generation drift and native package consumers. Filtered `sdk:test` runs remain partial. These controlled HTTP fixtures do not establish database, provider or complete product-journey qualification.

SDK checks report native typing, model/resource regressions, shared HTTP behavior, archives and installed consumers separately. The [current hardening evidence](../reports/sdk-hardening-verification.md) records interpreter versions, response-integrity regressions and local execution. Profile cancellation/startup/cleanup failures and incomplete call/witness inventories remain failures. These checks do not qualify skipped persistence/provider integration paths.

[Response-fix evidence](../reports/sdk-response-fixes-verification.md) additionally covers typed failure classification, status/media-specific schemas, malformed container bodies and default constructor/deadline behavior. Shared drivers use controlled explicit transports, so native construction tests establish the defaults separately.
