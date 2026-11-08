# Private HTTPS account qualification

This fixture runs the production account app and backend with real Kratos/Hydra providers and an existing admitted fixture human. Its eleven maintained native navigation cases passed in the pinned private-container/Chromium profile, with no failures, skips or cancellations and confirmed cleanup. It is isolated from the default HTTP development graph. This result does not qualify an OS browser, deliver packaged ingress #95 or complete #82. Registration, verification, recovery, account settings, configured MFA/OIDC, admission and remaining acceptance stay outside this supporting component.

Only the coordinator may launch the graph under an exclusive native qualification grant. Run the following command from the repository root in the pinned toolchain environment, with Bash, host Python 3.13 and an available Docker engine and Compose command. The repository selects Python 3.13.12. The host must provide POSIX `waitid` with `WNOWAIT`, process-group signalling and `ps`. Image builds need access to the pinned container images, locked package and Git dependencies, and the pinned Chromium download. The web image installs its own Node and pnpm, so the wrapper does not require them on the host.

Before admitting a development source build, the coordinator requires at least 20 GiB (`21474836480` available bytes) on both the container engine's storage filesystem and its host backing filesystem. This includes the 8 GiB build allowance, leaving 12 GiB after that allowance. Admission uses fresh observations and refuses missing space facts. Filesystem size and free-space percentages do not change this development floor. Production capacity planning retains its own requirements.

Before launch, reserve `172.30.82.0/24` and verify that it does not overlap another network. No other account fixture may use that subnet during this run. The volume comparison covers the selected runtime's full volume-name inventory, so unexplained changes from other activity also require reconciliation under the exclusive runtime grant. The wrapper defaults to Docker:

```bash
scripts/test-account-ui.sh --login-only
```

To select an available Podman engine and its Compose command instead, run this alternative from the same directory:

```bash
INFRAMELD_CONTAINER_RUNTIME=podman scripts/test-account-ui.sh --login-only
```

The declared dynamic allocation range is `172.30.82.128/25`, inside this subnet and separate from Caddy's fixed `172.30.82.2` address. Hydra continues to trust only `172.30.82.2/32` for proxy termination. Native qualification must verify that dynamic containers cannot take the gateway address, including when web or databases start first. This range does not permit overlapping or concurrent fixture runs.

Select exactly one of `--login-only` or `--recipient-proof`. An unsupported mode, runtime selection, missing runtime executable or unavailable Python 3.13 ownership capabilities exits 2 before creating fixture state or invoking the engine. The standalone Compose file supplies its environment directly. Do not copy or source `.env.example` or `profile.env.example` to launch the wrapper.

The script creates a private account directory, stages its web build context, then creates a new Compose project and image tags. It runs native password/code/browser boundaries, then attempts to remove its containers, networks, volumes and image tags. No ports are published. It never attaches provider logs.

## Run the closed recipient-proof profile

The same wrapper has one explicit profile for qualifying the shared Rust proof operation against the private stack. The selected Linux ARM64/rootless Podman native-driver result is recorded in the [verification report](../../../../docs/development/reports/recipient-proof-verification.md). Use the same pinned host prerequisites, exclusive runtime grant and private subnet reservation as above. From the repository root:

```bash
scripts/test-account-ui.sh --recipient-proof
```

For the selected Podman runtime:

```bash
INFRAMELD_CONTAINER_RUNTIME=podman scripts/test-account-ui.sh --recipient-proof
```

The profile source-builds both maintained examples into `/opt/account-proof/bin/recipient_proof` and `/opt/account-proof/bin/recipient_proof_native_driver`. It does not reuse an old host executable. Only the two fixed driver services get the private host/request/exec files. Their bridge/readiness volume is separate, and the browser gets no database, Hydra administration or exec-descriptor environment. The browser and both drivers share the long-lived backend's network namespace for literal loopback, while keeping private PID namespaces, `init: true` and runtime user `10001:10001`. A successful browser exit cannot tear down the drivers' namespace while maintenance or revocation is still pending. The backend fixture disables Uvicorn's proxy-header rewriting, preserving the application's existing gateway-only forwarded-header trust.

One original 300-second phase covers both fixed attempts and all three services: `browser-tests`, `proof-denied-driver` and `proof-driver`. First, the browser prepares `deny-ready`, then the denied driver must exit `1` with exactly schema version `1`, `error.kind: denied`, `error.resourceCleanup: not-needed` and `error.credentialCleanup: not-needed`. A generic failure is insufficient. An independent backend read must confirm zero receipt/grant/audit effects and unchanged Access revision and metadata before the positive driver can start. The `not-needed` fields describe the denial's obligations, not physical process/container cleanup.

The browser must remain nonfailed and publish the distinct `allow-ready` gate. Only then does `proof-driver` perform a fresh Allow attempt through generated session verification and real repair. Both readiness gates, both driver outcomes, the browser's final outcome and strict original receipt/database verification share the original deadline. No phase gets a new clock. Exact service IDs, project/service labels, runtime user and namespace facts must validate. A failed observation is not permission to signal a recorded ID or declare cleanup. The existing owner attempts cleanup after every failure.

The shared volume is mounted at `/run/account-proof`. Each attempt starts with a fresh mode-`0700` parent: `denied-bridge` and `bridge`, each containing its own mode-`0600` `browser.sock`. The public lifecycle markers `deny-ready` and `allow-ready` are separate from those parents. Each socket carries one same-UID authorization-ready event. Fresh PKCE, state and nonce remain inside the Rust owner. The driver-only input directories are `/run/account-secrets/recipient-proof-denied` and `/run/account-secrets/recipient-proof`, each with `host.json`, `request.json`, `exec.json` and an internal `expected.json` oracle. That fourth fixture file is not an operator input. The public example still takes only three files. These are two fixed qualification scenarios, not retries or an additional production mode.

## Retain the owner through phase cleanup

The public shell entrypoint delegates lifecycle control to the standard-library [Python owner](../../../../scripts/run_account_ui.py). Bash retains the fixed preflight, startup, inventory and cleanup function bodies. It does not wait for phases or signal saved process groups. Python runs each selected fixed phase in its own session with noninteractive input, and also owns the direct preparation, build and browser commands.

A phase leader can exit while one of its same-group descendants is still executing, even after closing stdout and stderr. The owner observes the leader without reaping it, so its identity remains retained while cleanup checks and stops that group. After its last possible group signal, it revokes signalling authority before collecting the leader's final exit status. Lost ownership permanently prevents later signals to that recorded number.

Process observations are bounded to one second within the existing stop grace and at most 4 MiB. Invalid, incomplete, timed-out or failed observations cannot establish an empty group. The observer also has its own wait owner. Missing quiescence or reap evidence keeps process cleanup incomplete. Neither a PID in a log nor a later process listing authorizes cleanup after ownership is lost.

## Follow the maintained startup sequence

The wrapper is the sole startup owner for this fixture. The Compose dependency declarations describe topology. The wrapper supplies `--no-deps` for startup and one-shot run operations so a dependent start cannot re-enter a completed TLS initializer. Direct Compose dependency startup is not an alternative procedure.

After its explicit image-build phase succeeds, the wrapper performs these stages in order:

1. Run `account-tls-init`, then `breach-tls-init`, exactly once against fresh project volumes. Both retain their nonempty-output rejection guards.
2. Start application/Kratos/Hydra PostgreSQL, Mailpit and the password-breach fixture. Wait for all three databases using their configured user/database and `pg_isready -h 127.0.0.1` inside each database container. The temporary Unix-socket-only initialization server is insufficient readiness.
3. Complete `hydra-migrate`, `kratos-migrate` and application `migrate`, in that order.
4. Start Hydra and Kratos, then complete `oauth-client-setup`, `identity-setup` and `seed`, in that order. The existing setup commands own provider readiness and fixture identity preparation.
5. Start backend, web and gateway only after setup succeeds. The separate browser phase runs only after the entire startup function succeeds and checks the public HTTPS surface before navigation.

Every stage shares the same original **180-second startup deadline**. Database polling and successive one-shots do not restart it. Persistent starts use `--no-build`, while one-shots rely on the image built in the preceding explicit build phase. One-shot containers use `run --rm --no-deps -T`. Each initializer, migration, setup and service-start exit status is checked. Its first failure prevents downstream work. Readiness probes may repeat until ready or the shared deadline.

The image runtime uses its already installed packages from `/workspace/apps/web` as UID/GID `10001:10001`:

| Process                       | Installed runtime command                                                    |
| ----------------------------- | ---------------------------------------------------------------------------- |
| Web                           | `node node_modules/next/dist/bin/next start --hostname 0.0.0.0`              |
| Identity setup                | `node --import tsx tests/fixtures/seed_identity.ts`                          |
| Untrusted-CA check            | `node --import tsx tests/fixtures/check-untrusted.ts`                        |
| Browser suite after NSS setup | `exec node --import tsx --test --test-concurrency=1 tests/browser/*.test.ts` |

These commands describe the maintained image entry points. Use the wrapper to start the graph. The runtime invokes Node directly and does not run pnpm dependency verification or installation. Locked pnpm installation and SDK/web builds remain part of image construction. Missing installed modules or build output fail the process and stop the run.

## Read the result and recover cleanup

Exit 0 requires the selected profile's assertions, confirmed cleanup of the owned processes, containers, networks, volumes and image tags, and an exact canonical volume-name match to a successfully captured baseline. Only then does `--login-only` print:

```text
Native account navigation checks passed. Cleanup confirmed. Combined Rust recipient-proof qualification is still pending.
```

On a successful `--recipient-proof` run, the corresponding message is `Native recipient-proof checks passed. Cleanup confirmed.` This is a conditional expected result, not a recorded native pass.

Public-context preparation, runtime preflight and Compose version checks each have a 30-second work budget. The proof profile prepares separate web and proof contexts within that same preparation budget and builds the backend, web and Rust proof images within the one 600-second build budget. Runtime preflight must complete both the engine version check and a sorted volume-name baseline before build or startup can begin. Build, startup and browser phases have respective 600-, 180- and 300-second work budgets. Cleanup has a separate 60-second work budget. Stopping an owned process group allows five seconds after TERM and another five after KILL if necessary, subject to operating-system scheduling. Repeated interruption does not restart phase stop deadlines or start another cleanup pass. Cleanup children retain normal signal handling and remain terminable. A zero cleanup-function exit alone cannot confirm cleanup if an earlier phase or observer lost ownership. An unresponsive process or unavailable container engine can leave resources that need coordinator reconciliation.

| Exit           | Meaning                                                                                                                                                                                                         |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `0`            | Selected-profile assertions and cleanup completed. A login-only pass does not qualify combined proof acquisition.                                                                                               |
| `2`            | Invalid invocation, runtime selection, a missing runtime executable or unavailable Python 3.13 ownership capabilities is rejected before fixture creation. A started phase can also return its own exit status. |
| `124`          | A bounded phase timed out.                                                                                                                                                                                      |
| `130` or `143` | The run received INT or TERM.                                                                                                                                                                                   |
| Other nonzero  | A phase failed, or cleanup could not confirm removal. Cleanup failure after otherwise successful phases returns `1`. An earlier failure or interruption status is preserved.                                    |

After fixture creation, phase and cleanup failures retain the private directory printed by the wrapper, even if resource cleanup succeeded. Its `context.txt` identifies the project, selected runtime, absolute Compose path, the backend/web image tags, exact `web_context` path, `volume_baseline_complete=true|false` and cleanup status. For the proof profile it also records `proof_image` and the exact `proof_context` path. Read this file as diagnostic metadata, never source it as a shell script. Its `cleanup.log` contains engine cleanup, inventory and image diagnostics, without attaching provider logs or native browser output. Successful runs remove the account directory and its owned staged context. Failure to remove that directory also returns nonzero and can leave only part of its contents.

At finalization, `volume_baseline_complete=true` records successful baseline capture and sorting. A false flag, missing canonical baseline, failed inventory or any exact volume-name difference makes cleanup incomplete. The inventories compare names, not just counts.

The private directory can retain `volumes-before.raw` and `volumes-before.txt`, `volumes-after.raw` and `volumes-after.txt`, and delta files `volumes-added.txt` and `volumes-missing.txt`. Raw output is sorted and deduplicated with `LC_ALL=C` for the canonical `.txt` inventories. Delta files are written when the comparison differs. Any of these files can be partial after failure or interruption. File existence alone proves neither successful capture nor clean removal.

If cleanup is incomplete, process ownership was lost or an owned process survived stopping, keep the subnet and qualification resource allocated until the coordinator reconciles the remaining processes and resources. Retain the original phase result together with the safe ownership and cleanup failures. Do not signal recorded PIDs or groups, infer release from output EOF or fixture self-expiry, or start another run as a cleanup substitute. Forced loss of the Python owner cannot produce a cleanup-success claim and may leave diagnostic files incomplete. A failed phase with confirmed cleanup still does not qualify the native journey.

Manual Compose removal can reconcile engine resources, but cannot prove that an earlier process owner completed. The coordinator can retry removal from the repository root. Replace the sample project and runtime below with the exact values from `context.txt`. Set `INFRAMELD_ACCOUNT_WEB_CONTEXT` to the exact recorded `web_context` value, preserving case. Do not derive it from the lowercase project name or create another destination. Verify that the Compose path below matches the absolute path in `context.txt`. For `--recipient-proof`, also set `INFRAMELD_ACCOUNT_PROOF_IMAGE` and `INFRAMELD_ACCOUNT_PROOF_CONTEXT` from the exact recorded `proof_image` and `proof_context` values before running Compose. Preserve both context paths rather than deriving them from the project name. These commands address only that disposable project:

```bash
account_project=inframeld-account-ui-example
account_runtime=docker
export INFRAMELD_ACCOUNT_BACKEND_IMAGE="localhost/${account_project}-backend:check"
export INFRAMELD_ACCOUNT_WEB_IMAGE="localhost/${account_project}-web:check"
export INFRAMELD_ACCOUNT_WEB_CONTEXT='/exact/recorded/web-context/path'
"${account_runtime}" compose -p "${account_project}" \
  -f "${PWD}/compose.account-ui.test.yaml" \
  --profile qualification down --volumes --remove-orphans
```

Check containers, networks and volumes for that exact project under both `com.docker.compose.project` and `io.podman.compose.project` labels. Remove only the backend/web image tags recorded in `context.txt` and, for a proof run, its recorded proof image tag. Verify that all those tags and project resources are absent. Confirm that the wrapper's owned processes have stopped before releasing the qualification resource or subnet. Retain the private diagnostics and any staged context until reconciliation is complete. A killed or incompletely cleaned run can retain public source under the recorded context path. After the coordinator confirms all owned processes and resources are gone and completes the volume-inventory reconciliation, remove only that run's owned account directory and context.

Project-label checks do not replace the full volume-name comparison. Reconcile added and missing names against a successfully captured baseline before releasing the runtime grant. A delta supplies no ownership or permission to delete a volume. Attribute unexplained changes first. The wrapper performs no automatic global-volume deletion or prune, and manual recovery must not delete names merely because they appear in a delta file.

After an initializer, migration, setup or startup failure, let the wrapper finish bounded cleanup. Reconcile any incomplete cleanup and retained volume-name differences before another attempt. Once the cause is corrected and cleanup is confirmed, a new wrapper invocation allocates a fresh project, volumes, TLS material and staged context. Never rerun either TLS initializer against populated volumes or weaken its fresh-output guard to continue the old run.

## Topology and configuration

`compose.account-ui.test.yaml` is standalone. The gateway has private IP `172.30.82.2` on `172.30.82.0/24`. Before launch, the coordinator must verify that this subnet is free. Hydra trusts only this gateway `/32` for TLS termination. There is no force-HTTP flag or broad proxy trust. Both public names resolve through private Compose DNS aliases.

| Public address                                                              | Fixed upstream              |
| --------------------------------------------------------------------------- | --------------------------- |
| `https://inframeld.account.test:8443/self-service/*` and `/sessions/whoami` | Kratos public `kratos:4433` |
| Same account origin `/v1/*` and `/.well-known/oauth-protected-resource`     | `backend:8000`              |
| Remaining account routes and compiled assets                                | `web:3000`                  |
| `https://hydra.account.test:8443/`                                          | Hydra public `hydra:4444`   |

There is no route to Kratos 4434, Hydra 4445 or private callbacks. The gateway owns forwarding and preserves Cookie, browser Origin, CSRF, native queries and Set-Cookie. It overwrites its forwarding metadata from the actual TLS connection, without proxy retries. Caddy access logs are off and the default logger discards account request diagnostics.

[profile.env.example](profile.env.example), [kratos.yaml](kratos.yaml), [hydra.yaml](hydra.yaml) and [Caddyfile](Caddyfile) describe the exact profile. These files contain disposable test-only credentials and must never configure a deployment.

The current Kratos/Hydra v26.2.0 image digests and runtime/generator pins remain unchanged. The gateway uses Caddy 2.11.7 Alpine at digest `sha256:e70b164da81ef698b3ad19af799ea6086ce6d9e48ed4079eb9fe26f6fbf14ee5`. The web image uses Node 26.6.0, pnpm 12.4.0 and locked dependencies. Playwright 1.64.1 pins Chromium 156.0.8078.4, revision 1248. The image installs that browser through the locked package.

The Caddy gateway runs as fixed UID/GID `10001:10001`. Its `/config` and `/data` tmpfs roots have mode `1777`. Before executing Caddy, the entrypoint creates private XDG directories `/config/inframeld` and `/data/inframeld` under `umask 077`, then verifies their `10001:10001:700` ownership/mode. The leaf TLS key remains mounted separately into the gateway.

Kratos migration and service containers have four distinct project-scoped named volumes: `kratos-migrate-home` and `kratos-home` at their respective `/home/ory` paths, plus `kratos-migrate-sqlite` and `kratos-sqlite` at their respective `/var/lib/sqlite` paths. These mounts cover image-declared paths while the provider database remains PostgreSQL. They belong to the disposable Compose project and still require the final inventory check. Provider startup and the covered native navigation cases passed in the pinned private profile. Combined Rust recipient-proof qualification remains pending.

The wrapper calls [the context preparer](prepare_build_context.py) before building. It copies six allocated public build inputs: root `.npmrc`, `package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`, `apps/web` and `packages/sdk-typescript`. The root `.npmrc` must contain only supported public pnpm policy, without registry credentials. Known environment, credential, cache and build-output paths are excluded. Remaining symlinks and non-regular source inputs are rejected.

For `--login-only`, the same 30-second preparation phase also reads only the fixed browser program from `manage-invitations/page.mdx`. Host SDK tooling's pinned esbuild bundles the unchanged TypeScript with the current SDK public source entry into a private-context `tests/fixtures/invitation-guide.iife.js`. It copies no host dependency tree or runtime secret into the image. The existing browser test injects that public IIFE with Playwright on the account origin and answers the literal program's dialogs. No new public route, browser module loader or alternate SDK transport is introduced. The recipient-proof context does not require this bundle.

The preparer copies [the fixture ignore rules](.dockerignore) to the disposable context root as its ordinary `.dockerignore`, so Docker and Podman use the same rules. It does not rely on a Dockerfile-specific ignore file or change the repository's backend ignore rules. No generated SDK source is edited. The image privately builds and consumes the selected TypeScript SDK. The proof profile stages a separate context containing the root Cargo manifests/toolchain, its Dockerfile/ignore rules, `apps/cli`, `packages/sdk-rust` and the existing Rust driver/fixture source trees. It source-builds the two examples without copying host binaries, credentials or caches.

`INFRAMELD_ACCOUNT_WEB_CONTEXT` is set by the wrapper to its exact private account directory plus `/web-context`. Compose consumes that path for the web image build, and `context.txt` records it for recovery. A normal preparation failure removes only the partial destination the helper created. A preexisting destination is rejected and preserved. Forced interruption can leave staged public source, so follow the recorded path and cleanup status instead of assuming the context was removed.

## Certificates and browser state

The locked integration image's existing `trustme` dependency issues one fresh 24-hour certificate with both public DNS SANs. The CA signing key exists only in generator memory. Only the gateway mounts the leaf private key. Public CA material is mounted into the disposable runner. Fingerprint and human fixture files are private to their required processes. Fresh volume initialization refuses existing contents.

The Chromium runner refuses preexisting legacy or modern NSS databases, including dangling links, and an unexpected `XDG_DATA_HOME`. It initializes an empty-password database at its disposable user's `$HOME/.local/share/pki/nssdb` before the first browser launch, with stdin closed. The browser must then reject the public origin before CA import. Only after that negative check does the runner import the CA and read back its nickname. It never initializes the database again after Chromium use. Three fixed completion messages identify these stages without native URLs or credentials. All browser contexts use `ignoreHTTPSErrors: false`, and the selected browser major is checked. The native navigation run exercised fresh NSS initialization, rejection before CA import and successful certificate import/readback with the pinned Chromium runner. This does not qualify other browsers or host trust stores. No host trust or DNS changes occur.

If the origin is accepted before CA import, or navigation fails after import, stop qualification and check the generated certificate's DNS names and expiry, mounted CA and pinned browser trust-store behavior. Keep certificate validation enabled while investigating.

The separate password-breach service reuses the repository's existing disposable HTTPS fixture and trust volumes. Mailpit retains the existing private STARTTLS/self-signed SMTP fixture settings. These are test-only provider settings, not a new public-client TLS exception.

`seed_identity.ts` uses the official Ory Identity API to create distinct fixture identities for the existing human, configured OIDC, recovery, identity switching and a recipient without a password. The dedicated schema also enrolls email-code identifiers. `backend.py seed` uses the existing first-administrator scenario with that exact seeded human UUID and the real bootstrap writer. Its controlled initial proof is fixture preparation, not host-bootstrap qualification, an injected browser identity or a substitute for authenticated product requests. Native Project/group creation, admission, issuance and revocation use the generated SDK with the actual signed-in issuer's cookie. Recipient operations and the literal guide use browser-owned cookies and Origin.

Registration, verification and recovery are enabled under native Kratos policy. The production recovery callback app and durable worker share `account_ui_test` and `kratos:account-ui-test`. Migration, native identity setup and bootstrap initialize the installation before worker startup. Three existing Jsonnet templates are mounted read-only. The existing private forwarding gate may interrupt a password-saved notification after real password persistence, then an explicit fresh settings flow in the bound recovery session continues delivery. Neither the forwarding gate nor the account page releases a block.

The forwarder's fixed test-only key is not an operator credential. Its runtime key file is `0600` under a `0700` directory owned by the callback UID `10001`. The generated Kratos hook overlay has the same private modes and the proven pinned-image UID `10000`, without assuming its GID or changing the provider user. Separate project volumes keep these files out of the web/browser services and public build context. All remain subject to ordinary project teardown and volume-inventory reconciliation.

The one 300-second browser phase includes a final independent backend session that checks the five recorded recovery/invitation outcomes. It checks consumption, one immutable original and activation audit, stable principal/link, attributed Project/group assignments, unused preview/denial state and real recovery proof/release. Observations contain identifiers and original result metadata, no invitation token or password. Failure prevents successful qualification and still enters the existing independent finalizer.

The harness uses no saved storage state, HAR, trace, video or screenshots. Raw provider errors are replaced with bounded test failures. It serializes browser scenarios so private email-code messages cannot race between tests. Session and CSRF cookies, native URLs and temporary email messages are necessary fixture state and are destroyed with the disposable graph.

## Evidence boundaries and remaining combined qualification

Controlled process substitutes exercise once-only fresh initialization, TCP-readiness gating, first-failure propagation, retained ownership and bounded startup cancellation/deadline handling. Syscall-boundary tests cover loss of wait ownership, signal-before-reap ordering, observer failures and repeated finalization. Finite fixture self-expiry is containment after assertions, not proof of harness cleanup. They execute no container engine or provider. These controlled checks are separate from the actual native navigation result below and do not establish combined recipient-proof qualification.

The maintained native cases cover password failure/success, explicit browser logout, code request/wrong-code/resend/completion/reuse/expiry, strict private-CA navigation, cookie scope/security, blocked public administration, safe missing consent and account response caching. The expanded account component adds native profile-first registration, verification, password persistence, configured cross-site OIDC and TOTP/backup-code challenges. These fourteen component cases have passed in the pinned private-container/Chromium profile with confirmed cleanup. Host entrypoint regressions use finite command substitutes, private HOME directories and real filesystem effects to check NSS order, EOF stdin, preservation and failure suppression. Those regressions do not run actual NSS or Chromium.

Native OIDC settings link/unlink and stale errors, recovery interruption/continuation, recipient activation/original recovery, changed identity and the literal browser guide are authored acceptance cases with execution still pending. Native execution is reserved for the coordinator and is not established by unit/type/build or cancelled-prompt bundle checks. Automated browser evidence does not perform human acceptance under issues `#371` and `#357`.

The four password/code Allow/Cancel cases passed through the real UI, checked Hydra continuation and exact registered loopback callback, including state and code-versus-denial validation. A test-only in-process Node receiver bound to literal `127.0.0.1` on an ephemeral port receives the actual redirect. It observes navigation without retaining a PKCE verifier or exchanging an authorization code for tokens, and performs no proof consumption. The fixture requires the delivered issuer-specific official registration rather than accepting the old shared callback. This test receiver does not substitute for the separate Rust authentication flow or complete #160.

The native revoked-session case passed: it signs out through Kratos, restores the old cookie in memory and requires a `401` consent refusal with no decision. Only an official `401` counts as unauthenticated. `503`, TLS, transport and timeout failures fail the check. Controlled expired-session `401` tests cover the same UI failure boundary. Neither the revoked-cookie case nor cookie clearing establishes natural expiry of the configured eight-hour session or a changed account.

`--login-only` deliberately does not assert complete recipient-proof acquisition. The [shared Rust capability and native-driver example](../../../../docs/development/guides/recipient-proof.md) are implemented. The [verification report](../../../../docs/development/reports/recipient-proof-verification.md) records the selected native-driver result and remaining operator limits. The combined test must consume the issuer-hashed callback contract and that same authentication operation through its private authorization-ready socket. The Rust driver and Chromium must share one disposable network namespace for the actual literal `127.0.0.1` listener. No callback proxy, copied OAuth implementation, saved credentials, Hydra-admin approval or injected claim may replace that handoff.

The [verification report](../../../../docs/development/reports/recipient-proof-verification.md) records the selected repair-only native-driver result and maps complementary controlled/provider evidence to the remaining qualification limits. Issuer/audience binding and CA/SAN/expiry rejection remain mandatory through the owning controlled/provider layers. Wrong/missing browser Origin/CSRF and expired/changed identity must reject without local mutation through their owning HTTP/provider boundaries. Uncertain cleanup remains unresolved.

The transient flow requests no `offline_access`, rejects unexpected refresh credentials and revokes only the tokens returned to that attempt. Independent login-chain preservation remains required. Existing provider coverage is [`test_selected_logout_preserves_independent_logins_and_browser_sessions`](../../../../apps/backend/tests/integration/access/test_hydra_cli_credential_lifecycle.py), parametrized with remembered consent both false and true. The [existing main provider integration run](https://github.com/matejpalenik/inframeld/actions/runs/41393681909/job/125111404580) supplies provider-semantics evidence. That earlier provider result is separate from the selected native-driver and credential-cleanup observations recorded in the verification report.

End-to-end remembered consent, ordinary refresh and saved-account lifecycle belong to the broader login qualification. Full #160 acquisition and the public operator recipe remain unqualified, with human acceptance tracked separately in [#240](https://github.com/matejpalenik/inframeld/issues/240) and [#298](https://github.com/matejpalenik/inframeld/issues/298). The latter retains the operator, rename and lost-response journey. The wrapper requires explicit `--recipient-proof` selection and does not promote a login-only pass into combined evidence.

Sources: [Ory passwordless code](https://www.ory.com/docs/network/kratos/passwordless/one-time-code), [Kratos cookie/CSRF behavior](https://www.ory.com/docs/oss/kratos/debug/csrf), [Chromium Linux certificate management](https://chromium.googlesource.com/chromium/src/+/main/docs/linux/cert_management.md), [Caddy TLS](https://caddyserver.com/docs/caddyfile/directives/tls), [Caddy forwarding](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
