# SDK response fixes and follow-up review

**Date:** 2026-10-27. This report records [ADR-0094](../../adr/ADR-0094-select-sdk-response-variants-and-safe-transport-defaults.md) and supplements [earlier hardening evidence](sdk-hardening-verification.md). Historical reports and results retain their original meaning. No historical Git revision is claimed for uncommitted artifacts.

## Result and architectural assessment

The selected SDKs preserve status/media-specific response shapes, expose honest failures and apply five-second buffered defaults. The tooling still uses ordinary typed workflows, shared Node feature tests and thin native drivers. No new HTTP wrapper, test language or plugin framework was introduced.

For example, Alice receives a ready model under HTTP 200 and a job model under HTTP 202. Swapping those bodies must fail. A declared nullable vendor representation can return null, while a declared bodyless response must remain absent. The operation's descriptors and native decoder select those alternatives before returning success. A validated error body cannot be substituted for a local network or decoding failure.

The fresh correctness and maintainability reviews found no unresolved material defects in the corrected paths after focused probes. Both independent reviewers rated the scoped architecture 9/10. These are architectural assessments, explicitly excluding missing CI evidence, rather than universal protocol or platform qualification.

| Category | Assessment | Reason and remaining cost |
| --- | --- | --- |
| Architecture and boundaries | 9/10 | Generation, native calls, shared assertions and packaging have distinct owners. Production packages remain independent of backend/generator tooling. |
| Correctness within qualified capabilities | 9/10 | Status, representation, null/body absence, failures and transport defaults have positive and negative regressions. This does not qualify arbitrary future OpenAPI shapes. |
| Typing and consumer usability | 9/10 | TypeScript failures narrow honestly, Python return unions preserve alternatives, and Rust exposes native response/error enums and metadata. |
| Testing and extension workflow | 9/10 | Every operation needs success coverage and native bindings. Independent witnesses check requests. Native typing, transport defaults, capability checks and installed consumers add separate evidence. Existing-field changes still require authored scenario review. |
| Maintainability | 8.5/10 | Pins, verified patches, operating routes and regression retention are explicit. Maintaining compiled generator assets and built-in resources remains real work. A newer-release upgrade rehearsal is still pending. |
| Scalability of endpoint delivery | 9/10 | Ordinary endpoints reuse the same pipeline and shared cases. New schema capabilities fail visibly and require reusable fixes. Driver bindings and meaningful business scenarios remain deliberate per-operation work. |

This is a strong SDK foundation for the future Rust CLI and public consumption. It is not proof that every future generator upgrade will be cheap. Keep the existing reconsideration trigger for broad analyzer/runtime redesign, repeated endpoint-specific exceptions or obstructive upgrade conflicts. No system can promise that future upstream releases will preserve all behavior automatically.

## Reviewed defects and retained fixes

All findings below were addressed in source/resource patches or faithful test observations, followed by regeneration where SDK output changed. No generated SDK output was repaired by hand.

| Severity | Finding | Resolution and regression |
| --- | --- | --- |
| P2 | TypeScript advertised API problem fields for network, local and decoding errors. | Exported `SdkFailure` distinguishes `api`, `http`, `decode`, `transport` and `request`. Native/static tests reject unsafe problem access before narrowing. Declared error bodies must pass their validator. |
| P2 | Response schemas were flattened across statuses and representations. | Verified parser/generator inputs retain each representation and its validator. Exact status precedes class/default, and exact media type precedes wildcard. Shared cases reject swapped bodies and ambiguous/incompatible representations. |
| P2 | Default constructors did not consistently enforce the intended timeout/redirect policy. | Five-second buffered defaults, no automatic redirects/redispatch, explicit overrides and cancellation ownership have emitted-runtime tests. Python scalar timeouts bound total collection, while tuples retain phase semantics. |
| P2 | Python could accept malformed JSON strings/arrays or turn malformed problem arrays into empty lists. | JSON and container shapes are checked before model conversion. Empty/malformed JSON, object/string array roots and malformed `errors` containers retain native failures and causes. |
| P2 | Python lost default selectors and annotated some bodyless-primary/default methods as returning only None or the first model. | Native response maps use `default`, and signatures derive unions from every successful/default representation, including null and body absence. Strict call-site assertions and temporary public-method probes cover these paths. |
| P2 | Rust lost secondary nullability, mixed bodyless alternatives and default-only payloads. | Native response enums preserve each body, unit alternative and nullable payload. Shared HTTP cases and separate default-only capability tests retain the evidence. |
| P2 | Rust typed errors selected only the first media schema or fell through an exact bodyless error to class/default schemas. | Status-owned media payload enums and native decoding preserve error alternatives. Exact bodyless declarations win, including empty and unexpected-body cases. |
| P2 | TypeScript body-read timeouts had HTTP classification, and caller-owned TimeoutError reasons could masquerade as the SDK deadline. | Collection remains a transport phase. Classification tracks the actual SDK deadline signal and first abort reason. Real loopback body-stall tests and caller-cancellation regressions pass. |
| P2 | Throwing error hooks discarded the original structured failure. | The aggregate cause retains the original classified failure/body or native cause alongside the hook exception. Returned diagnostics cannot forge trusted classification. |
| P2, evidence | Rust's generic JSON error observation claimed generated-model validation. | `serde_json::Value` reports parsed JSON, while generated error enums retain generated-model provenance. A shared undeclared-error case protects that distinction. |
| P2, test reliability | A mocked timeout case could stall, and a native HTTP probe could reset a connection during immediate close. | Timeout regressions use real loopback HTTP with explicit deadlines. The native probe reads complete bounded headers, half-closes output and drains input within its socket timeout. The framing regression and 25 repeated redirect checks pass. Assertions were not weakened. |

The native probe framing correction alone was insufficient. A subsequent full run still failed the native gate on a connection reset, while the other SDKs completed. Orderly socket shutdown/draining was then added and reverified. This failure remained visible rather than being retried into a green result or ignored.

## Inputs and reproducibility

The [manifest](../../../packages/sdk-tools/generators/manifest.json) owns selected versions, source identities, patch order and digests. Production pins, package identities, version 0.0.0, publication protection, root dependency locks and production OpenAPI remain unchanged. Preparation additionally verifies the already-locked Hey API shared parser in a private staged copy. Installed workspace dependencies are not patched.

Temporary snapshots retained 384 owned source/configuration hashes and prior evidence before editing. Historical comparison reports/results were checked against that snapshot and remain byte-identical. The production contract SHA-256 is `e8b3cb46d7de089319061f7920fec23df1a645401ce8021dfef921d3e174fed0`.

The [patch purpose/retirement table](../../../packages/sdk-tools/docs/generators.md#patch-purposes-and-retirement) and SDK skills explain ownership. Ordinary builds and `sdk:test` remain generation-free. SDK source changes come through explicit generation from verified inputs. The permanent commands retain their names and selections.

## Checks actually completed

The unfiltered `CARGO_NET_OFFLINE=true pnpm sdk:verify` passed for all three SDKs on local macOS. [Structured results](sdk-response-fixes-results.json) preserve that exact full verdict separately from subsequent deliberate drift probes and clean checks.

| Check | Observed result |
| --- | --- |
| Shared HTTP conformance | 80 cases per profile across Rust, TypeScript Node/Chromium and Python sync/async, 400 passing executions with no skipped or missing results |
| Handwritten typing | Strict shared/native TypeScript and Python Pyright/Ruff passed, with native Rust bindings and checked consumers compiled |
| Harness regressions | 45 Node tests passed, including checksum/patch rejection, coverage/result completeness, resource deadlines and cleanup failures |
| Native behavior | Rust 6 model and 5 lifecycle/probe tests, TypeScript 24 response/failure/default-transport tests plus 7 driver/resource tests, Python 18 model and 10 protocol/observation/lifecycle tests passed |
| Rust capabilities | 16 synthetic capability tests, 115 generator library tests and metadata-disabled external compilation passed, separate from shared HTTP counts |
| Backend | `pnpm check:backend` passed with 1,555 tests passed and 505 skipped, followed by 13 native OpenAPI tests. The SDK verification contract stage passed all 34 fixture/OpenAPI tests |
| Generation | Repeated explicit and clean temporary generation passed with all ordered patches and source/dependency drift checks |
| Deliberate drift | A temporary TypeScript generated-source marker failed drift checking while Rust/Python still passed. All 1,083 inventoried files stayed unchanged during the failed check. The marker was restored exactly |
| Clean non-mutation | Subsequent `pnpm sdk:check` passed for all SDKs and left the same 1,083 inventoried files byte-identical |
| Distribution | Crate, npm tarball and Python wheel built. Clean installed consumers exercised real success/error/recovery operations, native metadata and Python sync/async used-pool closure |
| Documentation/style | Root Prettier/backend formatting, handwritten Rust formatting, Markdown links/anchors and isolated `quick_validate.py` for all four affected SDK skills passed |

Actual local tools were Node 26.6.0, pnpm 12.4.0, Rust 1.95.0 and uv 0.12.15 on Darwin 25.3.0 arm64. Chromium reported 156.0.8078.4. Installed Python consumers used 3.11.15 and 3.13.12, both with HTTPX 0.28.1 and Pydantic 2.14.1. These are recorded run facts, not additional pin authorities.

The backend emitted one Starlette/AnyIO deprecation warning. Skipped integration coverage remains unqualified. No migrations or real provider calls were run. Repository-local UV cache selection avoided the restricted default cache without adding application dependencies.

| Tested archive | SHA-256 |
| --- | --- |
| `inframeld-sdk-0.0.0.crate` | `f5a8e42a671f594b05cf7732845b7df8990240c1fafab4f8e97de5e4ccc23f95` |
| `inframeld-sdk-0.0.0.tgz` | `ef242522b769cc71a84254056dcbae6344892ebd2e6d40cf20867397da2cd212` |
| `inframeld_sdk-0.0.0-py3-none-any.whl` | `994c2c7c43715204115ddd7501125b8733cc8c2c59bdda004d1f2e45ae1d3c13` |

Archive hashes identify the tested native archives. Native packaging is not promised byte-identical across timestamps or platforms. Deterministic source regeneration remains the drift gate. Test logs, per-case observations and standard reports remain under ignored SDK artifacts, while the linked structured evidence preserves the final verdict, stage statuses, runtime facts and archive identities.

## Fresh review evidence

Independent reviewers worked read-only with temporary schemas, generation outputs and probes. They did not edit repository source or overwrite shared artifacts. The correctness reviewer checked source/patch digests, generated public Python/TypeScript calls and types, and compiled Rust models plus unchanged emitted decoder blocks. Rust loopback execution was unavailable in that review sandbox, so its HTTP suite is author-run evidence. The maintainability reviewer independently checked private parser preparation and checksum rejection, hook evidence, a newly added status/model, README examples and concrete maintainer routes.

The final small provenance/probe corrections also received read-only inspection. Fragmented, incomplete and oversized probe input was independently exercised. No remaining material finding emerged within this review scope. This is a focused review of current APIs and extension mechanisms, not a claim that every possible contract combination has been tested.

## Issue #80 recommendation and limits

Architecturally, this is enough to close [issue #80](https://github.com/matejpalenik/inframeld/issues/80) for generated-client integration and incremental qualification after the implementation is reviewed and merged. The issue explicitly calls for delivered endpoints first, repeatable regeneration and later extension as domain endpoints arrive. Its scope does not require completing the CLI or the whole RAG product.

Durable jobs and receipts remain pending where production HTTP contracts do not exist. Synthetic fixtures qualify capabilities and do not deliver those workflows. Controlled HTTP tests do not establish database atomicity, real Kratos/Hydra journeys, production CORS or a complete CLI/account-UI journey. TypeScript's qualified fields/nonthrowing mode remains the primary promise. Limited throwing/data-only regressions do not establish broader response-mode qualification. Rust-only streaming capabilities are not inherited by other languages.

Linux and remote macOS execution remain pending. No CI workflow was dispatched, issue closed, registry package published or external repository setting changed. Broader server-version compatibility, release policy and CLI/login implementation remain separate work. The earlier newer-release upgrade-rehearsal limit remains pending and was not reclassified as completed.

## CI-bootstrap follow-up, 2026-10-27

The first PR checks at commit `e67e9cf99b01ee77125ccf60064aee60eab19edc` exposed two shared setup defects. In the [SDK run](https://github.com/matejpalenik/inframeld/actions/runs/40580297497), all six language/platform jobs stopped at the backend contract checks because no request-fingerprint key was configured. SDK verification never started. The aggregate correctly rejected their setup-only reports. In the [Quality run](https://github.com/matejpalenik/inframeld/actions/runs/40580297461), strict pnpm dependency approval rejected esbuild's installation script. These failures did not establish SDK conformance failures.

The workspace now approves only the already-locked `esbuild@0.28.2` build. Its pinned installation script was reviewed for platform-binary selection, version checks and download fallback. [Version-scoped `allowBuilds`](https://pnpm.io/settings/build#allowbuilds) preserves strict dependency approval rather than suppressing installation scripts. Both SDK installation commands run approved scripts, and workflow-level `HUSKY: "0"` skips Git-hook setup in verification and aggregate jobs. Package versions, lockfiles and other trust/release-age settings are unchanged.

Each verification job follows the existing backend CI procedure after Python setup: generate 32 random bytes in `$RUNNER_TEMP` under `umask 077`, then export only the absolute file path through `$GITHUB_ENV`. The key is outside the checkout and uploaded SDK artifacts. Required backend configuration and missing/malformed-key failures remain intact. The [SDK bootstrap instructions](../../../packages/sdk-tools/README.md#prepare-the-environment) link the existing local setup procedure. Changes to the SDK workflow or workspace build approvals now select macOS as well as Linux, so bootstrap-only changes receive all six jobs.

### Subsequent local verification

Checks used a disposable source archive of that commit with the scoped bootstrap edits, fresh pnpm stores and no pre-existing checkout dependencies or SDK build outputs. Generator source archives and native dependency caches were reused, while the default SDK tooling environment was prepared in the disposable checkout. This is clean JavaScript installation and local qualification evidence, not an uncached native build benchmark or remote platform evidence. The host's pnpm self-management cache initially contained a non-executable launcher. A private temporary tool cache was seeded with the installed, version-checked pnpm executable. No additional repository policy change or global tool installation was made to work around that local bootstrap issue.

| Check | Observed result |
| --- | --- |
| Strict install before approval | A fresh-store `pnpm install --frozen-lockfile` reproduced `ERR_PNPM_IGNORED_BUILDS` for esbuild 0.28.2 |
| Approved clean installation | Normal frozen installation from a separate fresh store passed. esbuild and unrs-resolver installation scripts ran, and actual esbuild transformation and tsx execution passed |
| Aggregate installation | The workflow's filtered frozen installation passed from another fresh store, followed by actual execution of its tsx loader |
| Configuration without key | The unmodified example configuration reproduced 7 failed and 27 passed contract tests because the fingerprint configuration was missing |
| Configuration with key | Executing the workflow's actual provisioning block produced a 32-byte file with mode 0600. All 34 contract tests then passed |
| Key failure regressions | All 33 existing application-settings and fingerprint-key-reader tests passed, including missing and malformed-key behavior |
| Quality | `pnpm format:check`, `lint`, `typecheck`, `test`, `openapi:check` and `build` passed. Turbo reported no cached task results |
| Backend | `pnpm check:backend` passed with 1,555 passed and 505 skipped tests, followed by 13 native OpenAPI tests |
| Platform selection | Temporary probes first demonstrated the omitted macOS selection, then passed for SDK-workflow-only, workspace-approval-only, lifecycle, SDK-documentation and unrelated-documentation changes |
| Complete SDK verification | `CARGO_NET_OFFLINE=true pnpm sdk:verify` ran every SDK independently but returned failure for TypeScript's native browser-cleanup regression. Rust and Python passed all stages. All other TypeScript stages passed |
| Shared HTTP conformance | All 80 cases passed in each of the five profiles, 400 executions with no skipped or missing HTTP results. This does not override the failed native gate |
| Native/package evidence | Default-layout strict typing, regeneration/drift, model checks, crate/npm/wheel archives and clean installed consumers passed for all SDKs. Rust capability, generator-library and metadata-disabled checks passed |
| Final consistency | Formatting and changed Markdown links/anchors passed. Only the four intended tracked files changed. Locks, generated SDK source and production OpenAPI remained byte-identical. No raw, hex or base64 test-key value appeared in 475 checked evidence/log files |

An initial full SDK run reused `INFRAMELD_SDK_TOOLS_DIR` outside the disposable checkout. Python's native typing stage failed because its Pyright configuration still resolves the environment at the default checkout-relative location. Runtime, packaging and consumer stages continued independently. Passing the actual environment explicitly to a diagnostic Pyright invocation removed those typing errors, confirming a separate custom-cache limitation. This optional-cache defect is not repaired by this bootstrap change. Use the default cache layout for complete qualification until it is corrected. The failed run is not counted as passing verification.

The default-layout full run exposed a separate intermittent failure in [the stalled-browser cleanup regression](../../../packages/sdk-tools/tests/native/profile-resources.test.ts). After `fixture.close()` rejected as expected, both the browser process's exit and signal codes were still null, so the termination assertion failed. A focused unchanged rerun with browser diagnostics passed. That diagnostic does not erase the full-run failure or establish its root cause.

The follow-up investigation belongs to [profile resource cleanup](../../../packages/sdk-tools/src/conformance/profile.ts). The outer browser-resource deadline and the combined graceful-close/forced-kill budgets both total five seconds, leaving a potential deadline race to investigate. This is a hypothesis, not a confirmed cause. [Playwright's kill contract](https://playwright.dev/docs/api/class-browserserver#browser-server-kill) includes waiting for process exit, so weakening the termination assertion would remove meaningful coverage. No lifecycle implementation, assertion, timeout or result-completeness policy was changed in this bootstrap fix.

Local full-verification acceptance is therefore still blocked by the browser-cleanup regression. Remote acceptance remains pending until all six updated SDK jobs execute verification, their strict **SDK conformance** aggregate passes, and Quality passes. No workflow was dispatched. Skipped integration tests, remote Linux/macOS execution and the existing upgrade-rehearsal limits remain unqualified. Historical structured results linked above retain their original run identity.
