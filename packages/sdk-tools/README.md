# Maintain the Inframeld SDKs

Start here when adding an API operation or fixing generated client behavior. This private development package generates the Rust, TypeScript and Python SDKs, tests their native calls against controlled backend routers, and checks their distributable archives. Customers do not depend on this package.

For example, changing consent must preserve `decision: "allow"` and `remember: true` on the wire. The [consent tests](tests/conformance/consent.ts) put that input beside assertions on the backend's independently recorded body. Each SDK's driver makes the call. The test decides whether it is correct.

## Find the right starting point

| I want to… | Start here |
| --- | --- |
| Understand the package | [Architecture and data flow](docs/architecture.md) |
| Add endpoint coverage | [Endpoint walkthrough](docs/adding-endpoint.md), then the relevant [feature test](tests/conformance) |
| Fix a generator or upgrade it | [Generator walkthrough](docs/generators.md) |
| Understand a native call | [Rust](drivers/rust/src/operations.rs), [TypeScript](drivers/typescript.ts) or [Python](drivers/python/operations.py) |
| Diagnose a failed check | The failing stage below, its log and its printed reproduction command |
| Understand qualification policy | [Shared SDK skill](../../.agents/skills/inframeld-sdks/SKILL.md) |

## Prepare the environment

Use the repository's pinned Node/pnpm, Rust and Python toolchains. The private process owner requires host Python 3.13 or newer, POSIX `waitid` with `WNOWAIT`, process-group signalling and `ps`. Run through the pinned environment so `python3` selects that host interpreter. This requirement is separate from the generated Python SDK's minimum version and its prepared test environments. Python generation also needs Java. Source preparation uses standard `git`, `tar`, `unzip` and `jar` tools. Install workspace dependencies with `pnpm install --frozen-lockfile`, prepare `apps/backend/.env.test` from its committed example and run `uv sync --project apps/backend --locked`.

The process owner uses only Python's standard library, launched with `-I -S -B`. It needs no SDK-tool cache or Python dependency installation to start. Missing runtime capabilities refuse target startup rather than falling back to unowned Node process signalling. This does not remove the backend, generator or SDK dependencies required by later stages.

The example test configuration does not include a fingerprint key. Follow the existing [fingerprint-key setup](../../docs/development/getting-started/local-setup.md#idempotency-fingerprint-key) and configure its absolute path before running backend contract checks or SDK verification. CI creates a separate 32-byte test key in each job's temporary directory and exports only its path. It does not use development keys or upload the test key with SDK artifacts.

Dependency installation runs only explicitly approved dependency build scripts. The workspace approves the pinned esbuild version used by the SDK tools. Keep strict build approval enabled and review a changed version's installation script before updating its approval. Do not suppress scripts to bypass a missing approval.

Run `pnpm sdk:setup` once to prepare all selected generators and development tools. Append `rust`, `typescript` or `python` to prepare one SDK. Python uses an isolated environment from [hashed tooling requirements](requirements.lock). TypeScript setup installs Playwright's full Chromium build for its [modern headless channel](https://playwright.dev/docs/browsers#chromium-new-headless-mode). Linux also needs `pnpm --filter @inframeld/sdk-tools exec playwright install-deps chromium`.

The default tool cache is `node_modules/.cache/inframeld-sdk-tools`. `INFRAMELD_SDK_TOOLS_DIR` selects another cache. `PLAYWRIGHT_BROWSERS_PATH` selects provisioned Chromium. Preparation verifies source and patch digests even when tools are cached. Downloads and installation are separate from SDK compilation.

Complete qualification supports either cache location. Native Python typing passes the selected cache to Pyright so it checks against the prepared `python` environment. The [CI-bootstrap follow-up](../../docs/development/reports/sdk-response-fixes-verification.md#ci-bootstrap-follow-up-2026-10-27) records the earlier default-path limitation, now superseded by this explicit selection.

## Commands

Run commands from the repository root. They default to all SDKs and accept one or more language names.

| Command | What it does |
| --- | --- |
| `pnpm sdk:setup` | Prepare verified generators and native test tools |
| `pnpm sdk:generate` | Explicitly regenerate production and fixture clients, staging output before replacing it |
| `pnpm sdk:check` | Regenerate temporarily and compare source, fixture schema and Rust dependencies without updating them |
| `pnpm sdk:test` | Type-check tooling, run tooling regressions, build native drivers, strictly check native drivers/consumers, run native regressions and shared HTTP tests |
| `pnpm sdk:verify` | Run drift, tests, available generator regressions, package builds and clean external consumers |

For a quick local iteration:

```sh
pnpm sdk:test --profile typescript-node --case consent-decide
pnpm sdk:test rust --case required-nullable-missing
pnpm sdk:verify
```

Profiles are `rust`, `typescript-node`, `typescript-chromium`, `python-sync` and `python-async`. Filters belong to `sdk:test` only. A filtered run is explicitly partial and cannot establish full verification. No match is an error.

The TypeScript native-regression stage uses the fixed [browser-owner fixture launcher](tests/native/fixtures/browser-owner.ts). It runs an independent worker-loss recovery probe before the original native test inventory. Use the maintained SDK commands above rather than running browser-resource test files directly with `node --test`. Those cases require the launcher's private owner context. Do not reconstruct it by supplying socket paths or capabilities manually. The launcher's fixed `profile` and `worker-loss-probe` diagnostic modes are internal, bounded partial checks, not additional SDK flags or complete qualification.

Ordinary SDK builds and `sdk:test` do not install or execute a generator. Cargo, the TypeScript package build and a standard Python wheel frontend consume committed generated source independently of the backend. Generation is always an explicit developer action.

## Read a failure

The workflows distinguish shared tooling checks, regeneration drift, compilation, native typing, model/resource regressions, HTTP behavior, generator regressions, archives and installed consumers. Python uses strict Pyright and Ruff from the isolated lock. Native TypeScript checking follows declaration building, so Rust/Python evaluation does not depend on successful TypeScript SDK compilation. One failed SDK does not prevent independent SDKs from running. Native response regressions also exercise default construction, timeout overrides, response-selection alternatives and failure classification independently of the shared drivers' explicit test configuration.

Tests use Node's standard runner and assertions. Shared HTTP case failures print their profile, name and reproduction command, with console assertions identifying expected and observed values. Native fixture diagnostics use the protected-evidence boundary below. Ignored `artifacts/` retains stage logs, per-case native output, JSON summaries, profile observations, backend logs and JUnit reports. A decoding failure can have HTTP 200 and still be a failure. A cleanup error also fails the run and must not replace the original error.

| Failure | Inspect |
| --- | --- |
| Checksum or patch failure | Original archive, patch bytes and [manifest](generators/manifest.json), before changing any digest |
| Drift | Native schema/configuration/patch changes and the listed differing files |
| Compilation/model failure | Generated signatures and native model checks |
| HTTP assertion | Feature test input, driver result and backend witness |
| Missing profile/result | Runtime availability, subprocess log and expected inventory |
| Packaging | Native archive metadata and external-consumer log |

### Read native fixture diagnostics safely

Native fixture stdout and stderr contain fixed JSON status records with `phase`, `category` and a known numeric `status` or `null`. Optional peer, case and capture metadata are validated fields. Terminal categories include `passed`, `failed` and `owner-unknown`. The fixture does not forward controller output, error messages, stacks or causes, even on success. Read the fixed phases alongside actual owner receipts to investigate assertion failure, peer loss and lifecycle order. They do not establish a cause or successful cleanup by themselves.

Protected diagnostics for the configured browser-owner report are allocated under `/tmp` as `<report-basename>.protected-<unique-suffix>`, outside the ordinary artifact tree. Nested timeout diagnostics remain beside their private case work directory. In CI these raw captures are job-local and may become unavailable after runner teardown. Use the owning run's custody record to locate the exact retained directories:

| Private location | Retained files |
| --- | --- |
| `/tmp/<report-basename>.protected-*` for the configured browser-owner report | `probe.raw.log`, `controller.raw.log`, `broker-status.json` |
| A sibling of the nested timeout case's work directory | `timeout.raw.log`, `assertion-status.json`, `worker-status.json` |

Directories have mode `0700` and files `0600`. The three raw captures are **PROTECTED RAW EVIDENCE**: unsanitized decoded command text that may be incomplete and is not a byte-faithful stream copy. `capture-checked` confirms file identity and encoded-size checks, not sanitization or completeness. Only the run owner and authorized reviewer should inspect these originals privately. Do not paste captures, publish excerpts or make redacted tails. `capture-unproved`, invalid or unavailable evidence remains a diagnostic limit. Recovery starts before diagnostic I/O and keeps its original deadline. Diagnostic collection or later physical reconciliation cannot turn a failed positive cleanup case into passing qualification.

## Generation inputs and patches

The [manifest](generators/manifest.json) owns versions, original archives, digests and ordered patches. [Language adapters](src/generation) own generator preparation and emission. [Rust options](generators/rust.toml) own its selected mode. Dependency locks own installed dependencies. Skills do not duplicate these pins.

Apply patches to verified generator source or built-in resources before generation. Never edit emitted SDK source or weaken native OpenAPI to make a client pass. The [generator walkthrough](docs/generators.md) explains the procedure and [shared maintenance policy](../../.agents/skills/inframeld-sdks/references/generator-maintenance.md) owns the obligations.

Rust's metadata-disabled consumer and synthetic binary/streaming/SSE/builder tests remain separate from shared HTTP counts. Published source-archive library tests do not establish an upstream integration suite absent from that archive.

## CI and proof boundaries

CI selects the existing `INFRAMELD_SDK_TOOLS_DIR` override under the job's temporary directory. setup-uv restores that same cache's `uv` directory, with the pinned Python version and explicit backend/SDK dependency inputs. Language-specific uv keys avoid competing matrix jobs saving incomplete subsets under one key. Every job still installs its dependencies and creates fresh consumer environments.

The [CI cache policy](../../docs/development/guides/testing.md#ci-dependency-caches) owns the cache inventory, key boundaries and cold/warm qualification procedure. SDK jobs restore the pnpm store and original generator archives. Rust jobs also restore compiled workspace dependencies and the content-addressed generator installation. Their platform/compiler key includes the manifest, actual patches and preparation code. Workspace crates, the generator's separate compilation directory and temporary consumer compilation directories are excluded. Source and patch hashes and the generator version are still checked on every preparation.

Each selected run performs regeneration/drift comparison, native checks, generator-library tests where applicable, archive construction and installed-consumer qualification. These operations produce fresh reports and evidence. Generator archives are reusable tool inputs, distinct from SDK package archives that must be built during verification. Do not cache generated SDK source, package outputs, virtual environments, Chromium installations, evidence or test results. Remote cold/warm performance remains unqualified until published runs are observed.

The workflow runs independent Ubuntu 26.04 language jobs for SDK/API-affecting changes, using the explicit `ubuntu-26.04` runner label. The existing pinned uv installs the pinned Python interpreter before key provisioning, without relying on GitHub's OS-specific Python builds. Generator, patch, configuration and platform-sensitive process/browser/lifecycle changes also select macOS. Changes to the SDK workflow or workspace dependency approvals select macOS too, so bootstrap changes qualify on both platforms. Manual qualification remains available. Its stable **SDK conformance** aggregate rejects failed jobs, partial runs and missing or incomplete evidence. Configure the external branch ruleset to require that aggregate separately.

The long verification jobs use the SDK input groups in the [shared CI selector](../../.github/scripts/ci_changes.py), through the [reusable change-detection workflow](../../.github/workflows/changes.yml). The [CI selection runbook](../../docs/development/guides/testing.md#ci-selection) owns shared comparison, fallback and full-run procedures. Unrelated changes run only lightweight change detection and the aggregate, with no SDK dependency installation, generator setup or runtime verification. Job-level selection keeps the required aggregate reporting, following [GitHub's skipped-check guidance](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks#handling-skipped-but-required-checks).

| Changed files | Long SDK verification |
| --- | --- |
| SDK code, tools, generators, patches, consumers, generated artifacts and fixture data | Run |
| Native OpenAPI, backend runtime source, contract tests, their controlled fixtures or backend test/dependency configuration | Run |
| Shared workspace manifests, locks, toolchain/build settings, dependency trust policy or SDK workflows | Run |
| Authored Markdown/MDX documentation, web-only code, database migrations or unrelated backend unit/provider-integration tests | Skip, unless the same change also contains a relevant file |

Backend runtime changes remain conservatively relevant because they can change HTTP behavior before OpenAPI is regenerated. Generated Markdown and Markdown fixture payloads remain artifacts, so they still select verification. When adding backend fixture dependencies, update the shared selector's explicit SDK input paths with the fixture imports. Shared selection changes and unclassified non-documentation inputs use the runbook's conservative full-verification policy.

The shared comparison retains earlier SDK changes in the same PR even after a later documentation-only commit. Manual execution qualifies the selected platform set, retaining the existing macOS choice. A successful not-applicable aggregate establishes only that SDK verification was not selected. It is not fresh SDK runtime evidence.

Tests use real production HTTP routers with controlled authentication/application collaborators. They do not call a database, real identity provider or paid endpoint. They establish SDK and HTTP-adapter behavior, not database atomicity, real Kratos/Hydra login, production CORS or a complete CLI/account-UI journey. Local macOS execution does not establish Linux or remote macOS execution.

The [dated rebuild verification](../../docs/development/reports/sdk-tooling-rebuild-verification.md) records the checks actually executed, failure probes and platform limits.

[ADR-0092](../../docs/adr/ADR-0092-maintain-sdks-with-typed-workflows-and-native-conformance-tests.md) records this architecture. [ADR-0091](../../docs/adr/ADR-0091-promote-selected-sdks-and-retire-generator-comparisons.md) retired comparison reproduction. Dated [Rust](../../docs/development/reports/rust-sdk-generator-comparison.md) and [TypeScript/Python](../../docs/development/reports/typescript-python-sdk-generator-comparison.md) reports preserve historical evidence. Their old commands and source locations are not current operating instructions. Publication, public transport-construction APIs and SDK/server compatibility remain separate work.

## Resource budgets and protocol evidence

The [budget module](src/system/budgets.ts) owns defaults: 30 seconds per case/startup, five minutes per profile, 20 seconds for overall cleanup, two seconds per control request and five seconds per resource cleanup. `SDK_PROFILE_TIMEOUT_MS` accepts an integer between 30000 and 3600000 for local diagnosis. Filters and overrides do not turn partial evidence into full verification. Commands bound captured output to 16 MiB and the backend log to 4 MiB, counting received bytes and failing visibly on overflow. Separate streaming decoders preserve UTF-8 characters split across chunks.

Command execution defaults to 900000 ms unless the caller supplies a timeout. Helper startup and control exchange consume that original deadline. Profile startup similarly retains one original 30-second deadline across browser acquisition, backend startup and readiness. A backend has a finite lifetime based on its profile budget plus cleanup, even if its Node controller stays alive without closing it.

`cleanupTimeout` is the complete stop-and-evidence budget, normally five seconds for a command or backend and 20 seconds for the enclosing conformance profile command. Its first stop fixes the deadline. Control delivery, TERM, KILL when needed, group observation, leader reap and stream completion share the remaining time. Repeated cancellation or close does not start another allowance. The owner reserves up to one second, or half a shorter budget, for escalation and final evidence. Backend TERM grace is at most 1.5 seconds within that same budget. Inner resource limits and an EOF fallback do not extend the enclosing profile's deadline.

### Diagnose incomplete cleanup

Suppose a profile times out after its backend leader exits but a same-group descendant is still executing. The [process ownership flow](docs/architecture.md#failure-and-resource-ownership) keeps the leader's identity until signalling finishes, so successful cleanup can stop that descendant whether it retains or closes the output pipes. A PID in a log is an observation, not a handle that authorizes later cleanup.

Keep the original command failure together with cleanup, control, observation and log-write errors. A successful target followed by unconfirmed cleanup still fails. Confirmed cleanup after a timeout does not turn the timed-out command into success. A missing owner receipt, failed process observation or forced loss of the profile owner leaves the affected resources unknown and held. Do not infer release from an empty pipe, an elapsed timeout or a missing PID.

For native browser-resource tests, the fixture launcher retains the actual BrowserServer outside the test workers. Its receipts distinguish profile-requested completion from emergency fixture recovery. A successful worker-loss probe establishes only the latter safety path. It cannot satisfy the positive profile-cleanup assertion or erase the original failure. Pending or rejected opaque acquisition, missing completion evidence or loss of the fixture owner can still leave browser resources unknown and held.

Stop affected qualification and retain its bounded logs and owning evidence for reconciliation. Do not send a late numeric PID/process-group signal, adopt a process from a marker file or rerun qualification as a cleanup substitute. BrowserServer cleanup belongs to its own Playwright owner, independently of backend group cleanup. Follow the existing [Testing guidance](../../.agents/skills/inframeld-testing/references/isolation-and-evidence.md) for maintained-command failures and host boundaries. This package adds no host-repair command.

The [shared qualification policy](../../.agents/skills/inframeld-sdks/references/shared-qualification.md#process-ownership-and-cleanup-evidence) defines the evidence needed for a passing cleanup result. Focused local process tests do not establish native BrowserServer/profile cleanup, Linux behavior or complete SDK qualification. Those require their actual maintained runs and applicable platform CI.

The private driver protocol records generated-model decoding, generated-schema validation, parsed JSON or no validation. It never equates an HTTP status with SDK success. Missing bodies and explicit null remain distinct. Native Python/Rust drivers read one strict versioned control document and write one reply, reserving stderr for diagnostics. Native HTTP models remain the generator's responsibility. Repeated headers and bytes stay native where available, while Fetch/browser normalization and hidden headers stay visible.

Case registration, scoped evidence and deletion bound witness state. The independent total counter detects untagged redispatch. Each feature declares its expected call count, and complete reports reject missing/duplicate calls and incomplete witness identities. Shared feature assertions remain the owner of business expectations.

[ADR-0093](../../docs/adr/ADR-0093-preserve-response-integrity-and-type-native-sdk-boundaries.md) records these boundaries. The [hardening report](../../docs/development/reports/sdk-hardening-verification.md) distinguishes actually executed checks, independent review, pending platform qualification and pending upgrades. A successful local run alone does not establish 9/10 qualification or issue closure.

Archive stages record the exact consumed archive hash. Installed consumers report actual runtime/dependency versions, including both Python roles, and Chromium reports its actual browser version. CI rejects missing runtime evidence. The Python minimum comes from the SDK’s `requires-python`, and the primary interpreter from `mise.toml`, through [the native environment helper](src/system/python.ts).

[ADR-0094](../../docs/adr/ADR-0094-select-sdk-response-variants-and-safe-transport-defaults.md) records typed TypeScript failures, status/media selection and safe buffered defaults. The [response-fix report](../../docs/development/reports/sdk-response-fixes-verification.md) records subsequent fixes and review, including local evidence and remaining platform limits.
