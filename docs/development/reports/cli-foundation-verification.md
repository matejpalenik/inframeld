# CLI foundation verification

Recorded 2026-10-28 in Europe/Prague. Work remains on issue/157, based on revision 14b000f6a19995d384d23e199be1e48e805f8736. Current artifacts explicitly report sourceDirty=true. Their revision identifies the checkout base, not a committed final delivery revision.

## Rust tooling replacement

The Python archive helpers and shell packaging driver have been replaced by the private Rust xtask. Local packaging and the four-platform CI workflow call the same cargo xtask package command. Production qualification uses explicit Result errors, with no assertions or debug assertions that optimization could remove.

The checked-in compatibility descriptor owns policy fields. Cargo supplies the version. The build script generates revision, target and dirty-source identity into one metadata document. CLI version output, archived metadata and native verification use that same document. The verifier rejects false release claims before executing the bundled binary and compares the binary's output against the exact archived metadata.

## Checks personally run for this revision

| Check | Result |
| --- | --- |
| Scaffold-first archive, metadata, tool-prerequisite and installation tests | Intended behavioral failures observed before implementing the affected behavior |
| Unexpected user-file regression | Intended failure observed, then complete user-state snapshot verification implemented |
| Rust formatting and strict Clippy for CLI and xtask | Passed |
| CLI integration tests | Seven passed, covering offline help, read-only home, usage failures, SDK behavior and compatibility metadata |
| xtask integration tests | Eight passed, covering normalization, corruption, wrong targets, false release claims, overwrite refusal, user-state preservation, evidence mismatch and missing tooling |
| Release-mode qualification regression suite | Five passed. Rejection gates remain active under optimization |
| Rustdoc with warnings denied | Passed for CLI and xtask |
| cargo-deny 0.20.2 | CLI and xtask advisories, bans, licenses and sources passed |
| pnpm check | Passed, including uncached CLI/xtask checks. Some unchanged backend/web/tooling results came from Turbo cache |
| pnpm build | Passed. CLI/xtask built, unchanged other packages used cache |
| Complete SDK verification | Initial run failed two existing Rust loopback lifecycle tests with IncompleteMessage. All other stages passed. The isolated lifecycle rerun passed five tests. The complete repeat passed all Rust, TypeScript and Python stages |
| cargo xtask package --reproducible | Passed locally on native Apple Silicon, with forced CLI recompilation between builds |

The first complete SDK failure is retained rather than reclassified as success. The subsequent unfiltered pnpm sdk:verify run completed successfully with partial=false. No SDK source or transport setting was changed to bypass it. Its precise transient cause has not been established. Earlier complete verification passed during the Python-backed foundation iteration, but that historical result does not replace current verification.

## Native artifact and reproducibility evidence

Environment: macOS 26.3.1 ARM64, Rust 1.95.0, cargo-dist 0.33.0. No Python is used by CLI packaging, testing or native CI qualification. The separate backend and cross-language SDK tooling retain their own Python requirements.

The native task passed checksums, payload validation, permission-denied installation, overwrite refusal, blocked destinations, paths with spaces, executable invocation and removal. It compared the complete temporary user's file state before and after. Archive reads reject unsafe/duplicate paths, links, unexpected payloads and oversized inputs. Child-process waits are bounded.

Two builds using the same source inputs, pinned toolchain, source-path remapping and source epoch produced identical normalized archive bytes, executable bytes and typed evidence:

- Target: aarch64-apple-darwin
- Archive SHA-256: 6d20aefa43f8af264f71183ddc5f9b89c8653f30514f00ff2e07aaabfb2428b8
- Executable SHA-256: a4a19937c4941f21e9224fb2623a149b2959d4d57146fa72b6abced416bb4ef6

This establishes repeated-build equality in this environment. It does not establish cross-host bit reproducibility or release compatibility.

## Remaining qualification

The workflow configures native Apple Silicon and Intel macOS 15, plus x86-64 and ARM64 Ubuntu 22.04. No remote workflow was dispatched. Those CI executions remain pending. The macOS 13 deployment flag is a build constraint and is no longer advertised as a qualified minimum supported OS. Local evidence covers macOS 26.3.1 only.

No release/tag, registry package or branch-rule setting was published. The development CLI remains version 0.0.0 and qualifies no released runtime pair. Full issue closure still requires the remote native matrix and final committed-revision evidence. Login, product commands, JSON automation and remote version enforcement retain their owning delivery boundaries.

## Historical evidence and guidance

The earlier Python-backed iteration passed repository checks, complete SDK verification and two normalized native archive builds. Review subsequently demonstrated that Python optimization disabled assertion-based qualification checks. That implementation has been removed, with debug and release-mode Rust regressions covering the defect. The original raw cargo-dist timestamp/ownership reproducibility defect remains covered by Rust normalization tests.

The ADR-0095 policy and its owning skill references remain accepted. Updated CLI directory guidance and development instructions route maintainers to the shared Rust task. The final Markdown check inspected 685 local targets with no missing files. Workflow YAML parsed successfully. Fresh skill-activation trials were not performed.

## Selected dependency baseline revalidation

The selected ADR-0096 libraries are now declared in the CLI and xtask manifests. The CLI owns terminal styles/streams, tables, progress and prompts. Insta is a development dependency. Completion/manual generators belong to xtask. Miette is optional behind the rich-diagnostics Cargo feature, with derive support and rich reports without backtrace capture.

Cargo.lock adds 48 packages without removing or changing an existing locked package version. This makes the libraries available. It does not implement the ADR-0097 source migration, shared presentation components, completion/manual generation or product automation.

The following checks were personally rerun after the dependency change:

| Check | Result |
| --- | --- |
| Locked CLI/xtask check with all targets and all features | Passed, including optional miette |
| Rust formatting and strict Clippy with all targets/features | Passed |
| CLI and xtask integration tests with all features | Fifteen passed, seven CLI and eight xtask |
| Optimized xtask qualification tests | Five passed |
| Rustdoc with warnings denied and all features | Passed |
| Default-feature CLI and xtask build | Passed |
| cargo-deny 0.20.2 for both manifests | Advisories, bans, licenses and sources passed |
| Native Apple Silicon packaging with forced repeated compilation | Passed, including installation/removal and complete isolated user-state checks |

The first sandboxed test invocation could not bind its isolated localhost listeners and failed with Operation not permitted. The full rerun outside that sandbox passed without test or application source changes. Dependency audits retained the configured warnings for multiple syn majors and, in the CLI all-features graph, multiple unicode-width majors. No policy exception or weakened gate was added.

### Updated local artifact evidence

The earlier archive hashes in this report precede the selected dependency baseline. This new native run used macOS 26.3.1, Rust 1.95.0 and cargo-dist 0.33.0. Its first and second typed evidence documents were equal:

- Target: aarch64-apple-darwin
- Archive SHA-256: 7c87e20adab9afa3d66b0bc1c6be7e08ded09d26a1bd60aae852e1c7078019b0
- Executable SHA-256: eed6ddcbff947b7918753723224b5bbcaaf54c1b643c229d3e8fdb3e65bd2363
- Compressed archive size: 265984 bytes
- Source revision: 14b000f6a19995d384d23e199be1e48e805f8736
- Source dirty: true
- Permission-denied installation checked: true

This is repeated-build equality for the local development worktree. It remains neither final committed-revision evidence nor qualification of another platform or released runtime pair. Complete SDK verification and full repository checks were not rerun for this dependency-only step. Their earlier results above retain their original scope.

The native CI matrix and final committed-source evidence remain required for issue #157. The compatibility decision is accepted locally through ADR-0095, while the GitHub issue still carries its older needs-decision label. Reconcile that tracking when publishing the accepted work. General JSON/dry-run contracts and implementation remain #156/#158, with login and target selection in their owning issues.

## PR #268 CI repair verification, 28 October 2026

The [PR checks](https://github.com/matejpalenik/inframeld/pull/268/checks) associated with head `01acf402416cac00bd5170ad2e8097298373b455` passed all four native CLI targets and the dependency audit. Quality and the three SDK jobs failed during frozen pnpm installation because the new CLI workspace had no lockfile importer. The SDK evidence aggregate then failed because those jobs produced no evidence. Backend integration separately reported 502 passed and three failed.

The repair adds only the empty CLI importer to pnpm-lock.yaml, without changing a locked dependency version. Pinned pnpm 12.4.0 initially left the missing empty importer unchanged during lockfile-only generation. After adding that entry, lockfile-only generation and both full and backend-filtered frozen installations passed with the existing supply-chain policies.

The original three recovery-worker scenarios passed unchanged on local Podman before the routing repair. A separate probe sent one saved execution-instance cookie to both private Kratos endpoints and received HTTP 200 from each. No cookie or response body was printed. This does not reproduce or explain the CI-only HTTP 401 rejection. The helper now explicitly verifies against the execution instance selected by those scenarios. Unit regressions cover default/selected endpoints, exact cookie forwarding, context-manager forwarding and rejection before OAuth authorization. Diagnostics retain the endpoint and status without reflecting credentials.

The external HIBP response-body timeout is removed from the test path through the selected local HTTPS fixture. Real Kratos still performs breach validation. The fixture returns a breach for one public test password and no listed breaches for other passwords. All test Kratos variants trust its dedicated CA and reject lookup network errors. TLS verification remains enabled. The existing runner deadline covers verified HTTPS readiness. The same non-root integration image serves the fixture, with no additional runtime, Python dependency or published port.

### Behavioral failure evidence

- Frozen installation reproduced the missing CLI importer error.
- Endpoint-selection and context-forwarding tests failed because the helper used the default Kratos instance.
- Six fixture tests failed against an API-only scaffold before its routes were implemented.
- Native registration tests failed before wiring: the fixture hostname was unavailable, and the designated test password was accepted rather than classified as breached.
- After wiring, seven focused native scenarios passed, including the original recovery failures and ordinary/breached-password registration.

The test TLS key is deliberately public and grants no deployment authority. Both certificates expire on 25 October 2036. [Fixture instructions](../../../apps/backend/tests/fixtures/password-breaches/README.md) own regeneration. Production password policy, application code, persistence and generated SDK source are unchanged by these repairs.

### Local repair results

Environment: macOS ARM64 with Podman 5.8.1, Python 3.13.12, pnpm 12.4.0 and the pinned repository toolchains. These checks ran against the local repair worktree:

| Check | Result |
| --- | --- |
| Full and backend-filtered frozen pnpm installations | Passed with unchanged supply-chain policies and dependency versions |
| Focused helper, breach-fixture and readiness regressions | 59 passed |
| Complete private integration suite | 508 passed, no skipped tests, in 232.01 seconds. Includes explicit CA-trust rejection and the original CI recovery failures |
| Backend checks | Formatting, Ruff, strict Pyright, fast tests and OpenAPI checks passed |
| Complete pnpm check | Passed. Backend fast tests: 1567 passed and 508 service-dependent cases skipped. CLI/xtask behavior checks ran uncached. Unchanged other tasks could use Turbo cache |
| Complete pnpm build | Passed. CLI/xtask rebuilt, with unchanged other packages using cache |
| Complete unfiltered pnpm sdk:verify | Passed for Rust, TypeScript Node/Chromium and Python sync/async. The evidence summary records partial=false and passed common/language stages, including archive and external-consumer checks |
| Test certificate chain and hostname | OpenSSL verification passed. Native tests reject the fixture without explicit test-CA trust |
| Documentation formatting, shell syntax and git diff checks | Passed |

An intermediate quality run caught a missing import in the added TLS regression. It was corrected before the final full suite. Strict typing also caught a private readiness-helper import, which was replaced by a public test-support function and rechecked without suppressions. The existing AnyIO deprecation warning remains. Sandbox network failures were rerun with the required local/network access, without weakening dependency or test policies.

The first pushed repair commit, `48e3e06`, exposed CodeQL findings for runtime SHA-1 calculations in HIBP test support. HIBP requires SHA-1 protocol values, but this fixture does not need to calculate them. The follow-up uses precomputed hashes/prefixes for public clean and breached test passwords. Real Kratos independently computes the protocol values, and the native tests verify both lookup observations and acceptance/rejection. All three native breach scenarios passed after that change, alongside the six fixture unit cases, Ruff and strict Pyright. No security query, scan gate or TLS check is suppressed.

The [PR checks](https://github.com/matejpalenik/inframeld/pull/268/checks) remain the authority for remote results on the revision being merged. Local Podman execution does not establish Docker CI execution, and the earlier green native CLI matrix does not qualify a later repair revision. Merge requires the applicable Quality, Backend foundation, SDK conformance and native CLI checks to pass on that revision. No test skips, blanket timeout increases, SDK-gate bypasses or production password-policy changes were introduced.

## Disposable integration TLS verification, 28 October 2026

This work supersedes the checked-in public certificates used by the initial PR repair above. The private stack now generates one CA and a 24-hour server identity per stack lifetime using the locked development dependency `trustme==1.2.1`. The proposed `1.3.0` pin was unavailable from PyPI, so the implementation uses the verified published release. Existing locked dependency versions remain unchanged. The only added packages are trustme, cryptography, cffi and pycparser.

The network-isolated initializer uses the existing integration image. It prepares fresh volume ownership as container root, clears supplementary groups and switches to UID/GID `10001` before key generation. Only the public CA is distributed to Kratos and the runner. Only the breach fixture receives the server key. The CA signing key is never exported. All consumers mount their material read-only, and verified HTTPS readiness retains the existing startup deadline. Teardown removes only the two exact-name, ownership-labelled TLS volumes and retains database volumes.

### Behavioral evidence

- All six new certificate tests failed against the API-only scaffold with `NotImplementedError`, then passed against generation behavior.
- Real TLS connections accepted the generated CA and rejected an incorrect hostname, an unrelated stack's CA and an expired server certificate. Tests checked the exact DNS identity, validity interval, exported files and permissions, plus rejection of non-empty output directories.
- Local Podman confirmed that the fixture runs as UID `10001`, reads a `0600` key owned by that user, and has no trust-volume mount. Both TLS volumes carried the expected ownership labels.
- Six native breach and recovery-worker scenarios passed, followed by both browser recovery-boundary scenarios. The public CA fingerprint remained identical across these repeated runs.
- Selecting the cached base Python image deliberately broke TLS initialization before provider startup. Startup exited nonzero, and cleanup left no project containers or disposable TLS volumes. Both named database volumes survived.
- Requesting a nonexistent test deliberately produced wrapper exit `4` after verified readiness. Teardown removed project containers and TLS volumes while preserving the database volumes.
- Sending TERM to the wrapper after verified readiness produced exit `143`. Teardown again removed project containers and TLS volumes while preserving the database volumes.
- A standalone initializer left volumes behind to simulate abrupt termination. The next full integration startup removed them and generated a different public CA fingerprint.
- An empty volume with the exact TLS trust-volume name but incorrect ownership labels caused teardown to fail visibly. The guard preserved it. The deliberately created negative-test volume was then removed explicitly.

### Checks on the implementation worktree

| Check | Result |
| --- | --- |
| Focused certificate, breach-fixture and readiness unit tests | 18 passed |
| Native breach and recovery-worker tests | 6 passed |
| Browser recovery-boundary tests | 2 passed |
| Backend checks | Passed. Ruff, formatting, strict Pyright, 1573 fast tests passed with 508 service-dependent cases skipped, and 13 OpenAPI checks passed |
| Complete pnpm check | Passed. Backend fast tests ran with the same counts. CLI/xtask and other workspace tasks passed, with unchanged tasks eligible for Turbo cache |
| Full private integration suite | 508 passed, no skipped tests, in 217.57 seconds. Successful teardown removed TLS volumes and retained both named database volumes |
| Shell syntax, documentation formatting and diff checks | Passed, including the final report update |
| Testing skill validation | Passed. Cleanup guidance was reconciled with the implemented lifetime. No discovery or activation rules changed |

Environment: local macOS ARM64 with Podman 5.8.1 and the pinned repository toolchains. Docker is not installed on this host. Docker CI and final-revision remote PR checks have not been run for this worktree. The earlier CI results above do not qualify these uncommitted changes. No production policy, generated SDK or Rust CLI behavior changed. The existing AnyIO deprecation warning remains.

## Superseded coordination experiment, 28 October 2026

Historical evidence only. The lock supervisor, worktree ownership protocol and dedicated lifecycle suite described in this section were subsequently removed. Their commands and guarantees are no longer supported. The serial-harness verification below supersedes this implementation.

The experimental shared stack used a standard-library `fcntl.flock` supervisor, launched through pinned Python 3.13.12 using uv. Commands acquired a stable per-user lock before touching stack resources. Nested calls validated the inherited descriptor and kernel lock. The wrapper retained ownership through cleanup, and a separate record protected a running manual stack between commands. Ownership records used atomic replacement. The lock inode was not removed during release. The recorded runtime was checked when switching between Docker and Podman.

The runner reports safe readiness categories without arbitrary exception text or response bodies. Public expiry metadata is exported beside the CA and checked before network readiness. Expired or incomplete metadata fails immediately with the exact stop, start and rerun sequence. Certificate verification and the shared 60-second startup deadline remain unchanged. TLS paths now live in neutral integration configuration rather than the generator module.

The removed `pnpm test:integration:lifecycle` command ran a host-side suite against the real scripts and a prebuilt private test image. Temporary JSON Compose overrides supplied controlled initializer failures and success, failure or blocking pytest cases inside the existing test image. No tracked test source was rewritten. The experimental Backend foundation configuration ran this qualification before the complete application integration suite without changing the job timeout.

### Behavioral failure and recovery evidence

- Four initial lock regressions failed against the scaffold, then passed with real competing processes, inherited-descriptor validation and abrupt-exit recovery.
- Eleven diagnostic tests failed against API-only scaffolds before implementation. Tests cover structured certificate errors, transport categories, expiry and missing or invalid metadata without reflecting injected sensitive text.
- The native initialization-failure scenario failed before override support because startup incorrectly succeeded. A separate initial fixture error was corrected first because Podman rejects creating an already-existing volume.
- A signing-key readiness regression observed missing HTTP failure classification before implementation. Successful readiness now clears previous failure state.
- A failed owner-record replacement test failed before atomic writes were added, then passed while retaining the previous owner record.
- All seven lifecycle scenarios passed on local Podman in 191.91 seconds. They covered controlled startup and test failures, successful teardown, cancellation, conflicting commands, stale TLS recovery and reuse, immediate expiry rejection, incorrect volume ownership and foreign manual-stack protection.
- Container termination events established that cancellation stopped the runner before providers. Database-volume creation identities remained unchanged through all scenario teardowns. Conflicting and foreign-worktree commands left the active container IDs unchanged.

### Historical coordination verification

| Check | Result |
| --- | --- |
| Complete host lifecycle suite on Podman | 7 passed in 191.91 seconds |
| Lifecycle checks after atomic ownership-record hardening | Initialization failure and foreign manual-stack protection: 2 passed, 5 deliberately deselected |
| Focused lock, diagnostics, TLS and readiness regressions | 30 passed before the final signing-key and atomic-record tests. Both added regressions subsequently passed in the full backend suite |
| Complete application integration suite | 508 passed, no skipped cases, in 241.49 seconds |
| Final backend checks | Formatting, Ruff, strict Pyright and OpenAPI checks passed. Fast tests: 1593 passed, 515 skipped. Skips are 508 service-dependent cases plus 7 dedicated host lifecycle cases, executed separately above |
| Final complete pnpm check | Passed. Backend fast tests ran with the same counts. Unchanged workspace tasks were eligible for Turbo cache |
| Shell syntax, documentation formatting and diff checks | Passed |
| Testing skill validation | Passed. No activation metadata changed. Source walkthrough and real positive/negative lifecycle scenarios support the updated guidance. No independent model activation trials were run |

Successful final teardown left no project containers, networks or disposable TLS volumes, and retained both named database volumes. A subsequent supported ownership check acquired and released the command lock successfully.

Environment: local macOS ARM64 with Podman 5.8.1 and pinned repository toolchains. Docker is unavailable on this host, so the newly added Docker CI step remains unexecuted locally. These local results do not establish final-revision remote PR success. No production behavior, generated SDK, Rust CLI or application password policy changed. The existing AnyIO deprecation warning remains.

## Serial harness simplification, 28 October 2026

This implementation replaces the superseded coordination experiment above with one supported local integration operation at a time. The Python lock supervisor, worktree ownership records, descriptor inheritance and Bash re-entry protocol have been deleted. The dedicated host lifecycle suite, its launcher, package command, Compose override interface and CI qualification step have also been removed. No compatibility aliases, dormant implementations or replacement ownership mechanism remain. Unrelated Access ownership logic and Indexing process safeguards are unchanged.

The Bash wrapper owns the automatic startup, test and cleanup sequence. Direct manual commands remain available without reservations. The wrapper is sourceable behind its main guard, with fast tests exercising its actual process and exit functions. Only the external cleanup operation is stubbed in those tests. Termination targets the entire active process group, including descendants whose leader has exited. TERM has a five-second grace period, followed by KILL and a further five seconds. The immediate child is reaped, surviving processes cause failure and original nonzero exit codes are preserved. INT and TERM retain `130` and `143`.

Deterministic breach responses, generated TLS, hostname verification, restricted key permissions, public expiry metadata, safe diagnostics and the 60-second startup deadline are retained. Exact-name and resource-label checks still protect TLS-volume deletion. Named database volumes survive cleanup. Backend foundation CI runs the application integration suite and a small post-run resource check, without a second lifecycle runner, new skips or a timeout increase.

### Behavioral evidence

- Refactoring the wrapper into a sourceable entrypoint preserved six existing exit/cancellation behaviors. Two new tests then failed against the original shutdown behavior: a TERM-ignoring child timed out and a grandchild survived after its leader exited.
- After bounded process-group shutdown was implemented, all eight wrapper process cases passed in 4.92 seconds. The focused wrapper, TLS and readiness group passed 33 tests in 6.51 seconds.
- The manual start/run/stop workflow passed all three native password-breach scenarios. Its public CA fingerprint remained unchanged during testing. The next automatic stack generated a different CA fingerprint.
- Manual teardown preserved both named database-volume creation identities. Existing commands stopped the prior implementation before switching. No process held its old lock. Two obsolete harness cache files and fourteen obsolete pytest cache entries were removed, along with deleted modules' generated bytecode and empty directories.
- The complete application integration suite passed 508 tests with no skips in 237.60 seconds. Normal teardown passed the CI resource checks, executed locally against Podman, and preserved both named database-volume identities.

### Verification

| Check | Result |
| --- | --- |
| Backend formatting, Ruff and strict Pyright | Passed |
| Backend fast suite | 1594 passed, 508 service-dependent cases skipped |
| OpenAPI checks | 13 passed |
| Complete pnpm check | Passed, with unchanged tasks eligible for Turbo cache |
| Workflow YAML and post-run Bash script | Parsed and passed Bash syntax validation |
| Local documentation links and Testing skill validation | 39 local links validated. Skill validation passed. Activation metadata was unchanged |
| Final real-stack smoke checks | Passed. Invalid pytest arguments returned 4, cancellation after verified readiness returned 143, and the active host process group was gone. Both runs passed the CI resource checks against Podman and preserved database-volume identities |

Current guidance now describes the serial workflow and unsupported local overlap. The only executable-interface references to the removed experiment retained in documentation are explicitly superseded historical evidence. No independent model activation trials were run for the focused Testing reference correction. Docker is unavailable locally, so Docker CI remains pending. Local Podman results do not qualify final-revision remote PR checks. Production behavior, generated SDKs, Rust CLI behavior and password policy remain unchanged. The existing AnyIO deprecation warning remains.

## Bounded automatic teardown, 28 October 2026

Automatic wrapper cleanup now runs once in its own process group, with disconnected stdin and a fixed 60-second work budget. The cleanup child resets EXIT, INT and TERM handling and disables nested job control. The parent continues shielding finalization. Cleanup timeout reuses the existing five-second TERM and five-second KILL grace periods, for a maximum nominal cleanup duration of 70 seconds excluding OS scheduling delays. The immediate child is reaped and remaining group members are terminated before return.

Successful tests followed by failed or timed-out cleanup return `1`. Existing nonzero results remain unchanged, including INT `130` and TERM `143`. Timeout reports potentially incomplete cleanup and the existing manual recovery command. Terminating the host CLI does not establish remote resource removal. Direct manual teardown, startup readiness, verified TLS, resource-label checks and database retention are unchanged. No new dependency, public timeout setting, retry, watchdog or coordination mechanism was added.

### Behavioral and real-stack evidence

- Before implementing the deadline, the selected hanging-cleanup regression failed with an outer `TimeoutExpired` after 13 seconds. Its bounded finalizer removed the controlled probe processes.
- All eight original process cases remain. Four added hanging-cleanup cases preserve prior statuses `0`, `7`, `130` and `143` as final statuses `1`, `7`, `130` and `143`. A fifth added case verifies KILL escalation for TERM-ignoring cleanup and its descendant. Assertions check process disappearance, process-group termination and immediate-child reaping. Only the external cleanup operation is stubbed.
- All 13 wrapper cases passed in 15.42 seconds. A final rerun after polishing the diagnostic message passed all 13 in 15.20 seconds. The focused wrapper, certificate, readiness and runner group passed 38 tests in 17.04 seconds.
- The complete private integration suite passed 508 tests with no skips in 234.74 seconds. The automatic wrapper returned `0`. The measured interval from pytest's final summary to wrapper exit was 11.62 seconds, including CLI return overhead and teardown, comfortably below the cleanup work budget.
- A real-stack runner-argument failure returned `4`, preserving the original failure through automatic cleanup. Sending TERM after verified readiness returned `143` in 19.49 seconds, including active-phase shutdown and teardown. Its recorded active host process group no longer existed.
- Successful, failed and cancelled runs passed the CI post-run resource assertions executed against Podman. No private project containers, networks or disposable TLS volumes remained. Both named database volumes retained their original creation identities throughout.

### Verification

| Check | Result |
| --- | --- |
| Backend formatting, Ruff and strict Pyright | Passed. No typing errors or warnings |
| Backend fast suite | 1599 passed, 508 service-dependent cases skipped |
| OpenAPI checks | 13 passed |
| Complete pnpm check | Passed, including CLI/xtask and SDK-tooling checks. Unchanged tasks were eligible for Turbo cache |
| Wrapper and driver Bash syntax | Passed |
| Workflow configuration | Parsed successfully. Post-run Bash syntax passed. No workflow change or timeout increase was required for this deadline |
| Documentation and Testing guidance | Formatting, local links and skill validation passed. This focused reference update changes no activation metadata. No independent model activation trials were run |
| Repository consistency | Diff checks passed. Removed coordination interfaces remain absent from executable code and current guidance. Explicitly superseded historical evidence remains above |

Environment: local macOS ARM64, Podman 5.8.1 and pinned repository toolchains. Docker is unavailable locally. Docker execution and final published-revision Backend foundation, Quality, SDK and native CLI checks remain pending. Local Podman evidence does not establish those results. No commit, push or workflow dispatch was performed. Production behavior, generated SDKs, Rust CLI behavior and password policy remain unchanged. The existing AnyIO deprecation warning remains.

A final spot check observed a new `pnpm test:integration` run started from an interactive terminal after these smoke checks finished. Its active resources were left untouched. The resource-removal results above describe the completed verification runs, not this subsequent run, whose outcome was not observed.
