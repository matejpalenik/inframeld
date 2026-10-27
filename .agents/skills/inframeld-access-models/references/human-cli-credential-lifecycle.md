# Store, refresh and revoke a human CLI login

<a id="store-refresh-and-revoke-a-human-cli-login"></a>

Alice closes the CLI and returns tomorrow. Her saved login is bound to one installation and verified human. Refresh can replace credentials for that identity, but cannot switch accounts or revive a credential invalidated by recovery.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="cli-login-transaction"></a>

<a id="complete-login-before-replacing-credentials"></a>

### Complete login before replacing credentials

For example, Alice already has a saved dev login when a new attempt fails after Hydra issues tokens. The failure must not destroy the old login or leave the new tokens silently stored. Treat login as a coordinated protocol and local-storage operation, not as a single successful browser redirect.

1. Freeze target configuration and account intent. Check the credential store before opening the browser where possible. A valid existing login may be reused. Login does not select a different target, account or project.
2. A maintained OAuth/OIDC library generates fresh PKCE material, state and nonce. Bind them to this issuer/client/redirect/target and keep transient secrets in memory. Never reuse them across login attempts.
3. Bind a temporary listener on literal `127.0.0.1` at an OS-assigned free port and the registered path. Open the system browser, not a WebView. No wildcard listener, LAN exposure or permanent authentication daemon.
4. Kratos authenticates the human through the Ory account UI. Existing browser sign-in may avoid another password prompt, but identity and consent remain visible. The trusted UI integration uses documented Ory APIs and official clients. It does not issue its own tokens.
5. Validate the callback's association with the pending transaction before exchanging the code. Validate the returned ID token's signature, issuer, audience, expiry and nonce through the maintained library. Tokens arrive at the token endpoint, not in a browser redirect.
6. Where first-local-setup bootstrap is needed, perform the separately authorized host-maintenance claim after verified identity and before product admission. Then call the implemented `/v1/session` operation using the access token. Require an admitted, active human and use its stable principal ID. This operation supports cookie and human bearer authentication, while bootstrap remains a separate capability.
7. An existing account alias must resolve to the same verified identity. A new alias requires visible confirmation. Atomically save the new coherent credential set only after validation and admission, and only if the captured local credential revision still matches.
8. Close the listener and discard transient secrets. A minimal callback page may say to return to the terminal, but must not claim admission succeeded before the backend check. Use no third-party assets and redact callback query strings.

For multiple issuers, qualify the standard issuer-response check or another standards-documented mix-up defense. State matching alone does not settle that defense. Reject malformed/repeated callbacks, bound waiting time and do not blindly retry an ambiguously consumed authorization code.

| Outcome | Credential and user-visible result |
| --- | --- |
| Cancellation, denial or timeout | Preserve the previous login. Close listener/stop polling. Nonzero result |
| Issuance followed by admission denial, storage failure, identity mismatch or concurrent local change | Attempt standard revocation of newly issued credentials at the already-trusted issuer. Preserve previous login. Report unconfirmed cleanup without persisting abandoned tokens |
| Successful replacement | Commit the new login atomically, then revoke the superseded chain using standard token revocation, not account-wide consent deletion |
| Old-chain revocation fails after replacement | Keep the new login. Report `New login saved. Previous session revocation unconfirmed` with a nonzero partial outcome. Never restore a possibly revoked old token |
| Crash after replacement but before old-chain revocation | Old server credentials may remain usable until expiry/operator revocation. Document this limit, not a hidden persisted revocation queue |

Keep old credentials only in protected memory while completing replacement cleanup. Failure cleanup must never revoke the previous login instead of the abandoned new one.

Device authorization is an explicit alternative, not an automatic fallback after browser launch fails. The proposed `login --device-code` obtains the verification URI/user code from Hydra, asks the human to approve only the matching requested code, keeps the device credential private and respects polling intervals, slow-down, denial and expiry. Before qualification it returns unsupported without issuing credentials. The proposed `--no-browser` merely prints the desktop authorization URL while retaining its loopback callback. It is not a general SSH/remote-host solution. A local issuer is not exposed publicly to make either flow work.

<a id="cli-credential-lifecycle"></a>

<a id="store-refresh-and-revoke-one-bound-login"></a>

### Store, refresh and revoke one bound login

Use maintained adapters for macOS Keychain and Linux Secret Service. Initial qualification targets are macOS Apple Silicon/Intel and Ubuntu 24.04 LTS. Exact minimum versions and Linux architectures belong in the release matrix. Native Windows is deferred. WSL2 and headless human persistence require independent qualification. A missing, locked or unusable store fails with repair guidance, never plaintext fallback.

Non-secret settings may store labels, URLs, verified IDs and saved selections. They must not store passwords, tokens, PKCE verifiers, cookies or provider keys. Human OAuth login has no token-paste mode. Application-key hidden entry/file/stdin is a separate credential path. Lists, JSON, debug logs, HTTP traces and crash diagnostics must not expose secret values.

Use one per-target/account lock and reload the latest credential value before refresh. Account aliases for the same bound principal resolve to one credential entry, not competing rotating-token copies. Selection/credential writes must be atomic. Do not hold the lock while a human is in the browser. Compare the saved revision before committing a completed login. A concurrent logout or login causes a conflict instead of silently overwriting newer state.

Ordinary commands refresh quietly when possible and otherwise print the exact target/account login instruction without opening a browser. Strictly rotate refresh tokens with **zero refresh reuse grace**. Commit the replacement access/refresh pair as one coherent value. A lost refresh response or crash after rotation but before saving requires login unless qualified standard behavior proves safe recovery. Never blindly replay the old token, disable rotation or delete another process's newer credentials. Do not decode opaque tokens or extend expiry locally.

| Lifetime | Accepted default | Owning service setting |
| --- | --- | --- |
| Access token | 5 minutes | Hydra `TTL_ACCESS_TOKEN=5m` |
| Refresh token | 7 days from issuance or last successful refresh | Hydra `TTL_REFRESH_TOKEN=168h` |
| Authorization code | 1 minute | Hydra `TTL_AUTH_CODE=1m` |
| Browser session | 8 hours | Kratos `SESSION_LIFESPAN=8h` |
| Interactive CLI wait | 10 minutes | CLI UX timeout. Exact option remains a contract deliverable |

These are service-container settings, not CLI secret-input environment variables. The [configuration boundary below](#provider-lifetime-configuration) supplies the four provider defaults and their validation. Client provisioning removes per-client lifetime overrides. A duration change does not revoke existing tokens.

Alice logs in Monday at 09:00. Her access token expires at 09:05 and refresh token the following Monday at 09:00. A successful refresh Thursday at 09:00 issues a replacement expiring the next Thursday. Selecting a target, leaving a terminal open or doing work that needs no refresh does not move that deadline. There is no idle keepalive or separately selected absolute login-age cap.

Repeated legitimate refresh can maintain login for weeks. A stolen current refresh token remains a risk until revocation, replay detection or another check stops it. A browser-session expiry does not cancel this separate OAuth grant. A future absolute cap needs qualified server enforcement, not a client timer.

Authentication recovery never authorizes retrying a possibly paid/mutating operation. Retain the original business operation identity and uncertainty rules. Repeated refresh is not a remedy for permission denial.

The proposed `logout --target dev --account alice` revokes and removes only this machine's selected dev/Alice credentials. Omitted selectors resolve the effective context, never all accounts. Do not delete all consent for the human/client: that could affect independently established logins. Qualify related-token invalidation and independence of logins on separate machines. If supported integration cannot provide that lifecycle, report the limitation before release rather than promising narrower revocation.

Even when Hydra is unreachable, remove the selected local credentials and return a nonzero partial result explaining that remote revocation is unconfirmed. Do not retain a hidden plaintext retry copy. A pending login/refresh must not restore a logged-out entry. Leave selections intact and the account selectable but logged out. Never switch automatically to another signed-in user. CLI logout does not sign out browsers, remove accounts, revoke application keys or log out other machines.

Account switching uses `account use`, not `login --reauth`. Existing-alias reauthentication must prove the same identity. A reused browser session cannot rebind Alice to Bob. The Ory account UI handles changing browser identity, not cookie manipulation or an assumption that `prompt=login` chooses another user.

Verified password recovery/reset invalidates old Kratos sessions and affected Hydra grants under the [recovery cleanup contract](recovery.md#identity-recovery-cleanup). Product access stays blocked until both required outcomes are confirmed. An otherwise active human then resumes automatically. A suspended human still needs deliberate authorized restoration. Requesting a recovery email anonymously must not revoke access. Preserve the legitimate new recovery session so recovery can finish. Exact hook delivery, ordering and durable partial-failure recovery remain specification work, not a promise that either identity product revokes the other's credentials automatically.

<a id="cli-authentication-qualification"></a>

<a id="qualify-authentication-without-inventing-another-protocol"></a>

### Qualify authentication without inventing another protocol

The security baseline is RFC 9700 with the explicitly bounded local-development transport exception. Assess supported sender-constrained tokens such as DPoP and record bearer-token residual risk. Do not invent DPoP or claim availability without qualification. Use maintained OAuth/OIDC libraries for protocol verification and generated application clients for business calls. No custom issuer, cookie scraping, token relay, embedded client secret, public client registration, new MCP OAuth discovery or permission-bearing OAuth scopes is introduced.

Before release, and require evidence for all of these behaviors, not just a happy-path browser screenshot:

- Password/configured existing OIDC methods resolve the intended stable Kratos-linked principal without email merging. Additional SSO onboarding remains deferred.
- Configured MFA and verified recovery preserve admission/suspension boundaries. Anonymous recovery requests cannot revoke credentials.
- Missing/plain/wrong/cross-transaction PKCE proof and code reuse fail. Wrong state/issuer/client/nonce and malformed discovery/ID tokens fail before credential commit.
- Only the permitted loopback host/path/port variation works. Canceled login closes its listener.
- Wrong token audience/client/scope/kind, inactive/expired tokens, disabled Kratos identities, missing admission and suspended/retired/application-kind principals are rejected. Provider uncertainty fails closed without a held application transaction.
- Concurrent login/refresh/logout, credential replacement cleanup, changed target bindings, strict rotation, lost responses and crash-before-save preserve the documented outcomes. No preference change retargets admitted work.
- Every supported OS store, headless mode if offered and credential-input channel is tested for unavailable-store failure and secret-safe output. JSON and diagnostics contain no tokens.
- Independent-login revocation, browser/CLI lifecycle separation, rolling expiry and deployment duration overrides are verified, not inferred from a generic Ory feature description.
- Device approval/denial/expiry/slow-down/repeated or concurrent redemption and OIDC results pass for the selected OSS build before enabling that flow. Shared token failures still block all affected modes.
- Managed-local isolation, private admin services, proxy bypass, hostile origins and remote HTTPS/cookie/CSRF behavior are qualified separately. Local HTTP success proves no production TLS behavior.
- Bootstrap is operator-bound and one-time/concurrent-claim safe. Public first signup cannot claim administration.
- Noninteractive commands never start human flows. Competing credential mechanisms fail. Cookie CSRF is retained. Human and application credentials cannot be confused.

Use 0 for success, 2 for usage errors and 1 for other ordinary failures. Precise signal/JSON contracts remain deliverables. Missing target/account/credentials produce explicit context-specific guidance, not fallback or surprise browser launch. `--no-input` is checked before interactive work. Invalid credentials map to 401, valid but unadmitted/ineligible humans to 403, and unavailable/malformed provider verification to 503 for the human-session operation. Ordinary product visibility rules remain unchanged. Saved-login replacement/logout cleanup uncertainty is a nonzero partial outcome, not success.

Exact compatible version/digest pins, release advisories, managed origins, maintenance IPC, issuer mix-up defenses, remaining lifespan keys, wire schemas, OS matrix and recovery-hook sequencing remain engineering/qualification deliverables. The historical inspection of Hydra v26.2.0 was a candidate observation, not a permanent pin or evidence that later fixes exist there. Qualify a suitable maintained OSS release without floating tags, surprise startup upgrades, private protocol forks or silently switching to a paid distribution.

### Provider lifecycle coverage

The [real-provider lifecycle scenarios](../../../../apps/backend/tests/integration/access/test_hydra_cli_credential_lifecycle.py) exercise the digest-pinned Hydra v26.2.0 test stack. They verify rejection of missing/plain PKCE and an omitted challenge method, missing/incorrect/cross-flow verifiers, and reused authorization codes. Legitimate refresh replaces both secrets while preserving the subject, issuer, client, audience and installation/version metadata.

Reusing a code or old refresh token revokes its affected login chain. A successful refresh response discarded before delivery leaves the caller without the replacement pair. The test explicitly probes reuse and obtains fresh credentials through another login. That probe is not an automatic retry strategy.

Revoking the selected current refresh token through public `/oauth2/revoke` invalidates that login's credentials. Repetition preserves Alice's independent desktop and remembered-consent grants, her Kratos browser session, Bob's login and another client's credentials. Tests inspect activity and attempt refresh rather than inferring revocation from an empty success response.

These scenarios use private test client registration and test login/consent approval. Separate [production provisioner tests](../../../../apps/backend/tests/integration/access/test_hydra_cli_provisioning.py) exercise installation reconciliation, callback restrictions, default and overridden deadlines, rolling refresh expiry and actual authorization-code expiry. The CLI's credential storage, replacement and logout interaction remain separate deliverables. Recovery's broader bulk cleanup remains unchanged.

<a id="provider-lifetime-configuration"></a>

### Configure provider lifetimes at installation

Development Compose passes the same four effective primary settings to provider startup and the provisioning preflight. [`IdentityProviderLifetimeSettings`](../../../../apps/backend/src/inframeld_backend/access/infrastructure/settings/identity_provider_lifetime_settings.py) accepts positive finite native durations with ASCII digits within the provider's signed 64-bit nanosecond range. Zero, negative, unlimited, malformed, non-ASCII and overflowing values fail before provider I/O. Valid ASCII inputs are preserved exactly. These settings do not belong in business Commands or bearer-verification policy.

The following other timers retain native defaults in the pinned v26.2.0 releases. They are not new Inframeld product defaults:

| Purpose | Native key | Pinned default |
| --- | --- | --- |
| Hydra ID token | `TTL_ID_TOKEN` | `1h` |
| Hydra login/consent request | `TTL_LOGIN_CONSENT_REQUEST` | `30m` |
| Hydra remembered login | `TTL_AUTHENTICATION_SESSION` | `720h` |
| Kratos login, registration, settings, recovery and verification flows | `selfservice.flows.<flow>.lifespan` | `1h` each |
| Kratos recent authentication for sensitive settings | `selfservice.flows.settings.privileged_session_max_age` | `1h` |
| Kratos recovery/verification link or code | `selfservice.methods.<link or code>.config.lifespan` | `1h` |

The inventory comes from [Hydra's configuration schema](https://github.com/ory/hydra/blob/v26.2.0/.schema/config.schema.json) and [Kratos's schema](https://github.com/ory/kratos/blob/v26.2.0/embedx/config.schema.json) and [configuration accessors](https://github.com/ory/kratos/blob/v26.2.0/driver/config/config.go). Native Kratos session lifespan is `24h`, explicitly overridden to `8h` here. The expiry-only test instance retains `15s`. Optional native timers remain provider-validated. The focused preflight validates the four primary settings, not every provider option.

Remembered consent is separate: Inframeld's server-controlled approval duration defaults to 3,600 seconds. Reusing that approval must not extend it, and it does not extend token or browser-session deadlines. Hydra's remembered login does not bypass Inframeld's current Kratos session checks.

Apply changed provider environment/configuration by recreating the providers while preserving their databases. Rerunning client provisioning alone does not apply new provider environment values. Existing credentials keep their recorded deadlines. Reconciliation and restart are not revocation. [Local setup](../../../../docs/development/getting-started/local-setup.md#configure-the-cli-client) explains the commands and private administration boundary.

<a id="human-credential-versions"></a>

<a id="keep-an-old-cli-login-invalid-after-recovery-finishes"></a>

### Keep an old CLI login invalid after recovery finishes

Alice's CLI approval captures version 6, then recovery advances her to 7. Even if the delayed approval later creates an active Hydra grant, Inframeld rejects its version-6 credentials before and after the temporary block is released. Refresh preserves 6. A fresh verified login can receive 7. Bob is unaffected. [ADR-0072](../../../../docs/adr/ADR-0072-version-human-cli-credentials-across-account-recovery.md) records this boundary.

The implemented allow path reads and validates the trusted Hydra request before initializing/capturing state. It then verifies the current browser identity and rereads version and block. Both observations must be unblocked and match the same identity, installation and version. An initially blocked attempt cannot become approved simply because its block clears during verification. The SDK receives the captured values, even if its call completes late. Inspection and denial use a separate read-only path and do not initialize state.

Hydra stores `inframeld_installation_id` and `inframeld_credential_version` in access-token session metadata. The browser never supplies them. Private introspection returns them to the verifier. Bearer authentication checks current identity and local state, then carries its exact non-secret binding in the actor context. Both authorization families also check current binding facts before work or replay using their existing transactions. Readers report the checked actor/installation relationship and current version, while the shared evaluator interprets evidence and the domain policy decides currentness. [Credential query and policy boundaries](eligibility-and-current-authority.md#credential-query-and-policy-boundaries) explain these responsibilities. Cookie and application credentials keep their existing paths. No positive authentication cache is introduced.

Stale, unversioned or invalid CLI bindings return the generic `401 http_error` with a Bearer `invalid_token` challenge. A valid binding still receives ordinary 403 eligibility/permission decisions. Required unavailable state returns 503. Tokens, versions and recovery details do not enter public error messages.

New recovery admission advances the version atomically with the original obligation and block. Duplicate delivery and completion do not advance or reset it. Independent flows each advance it and release only their own block. Missing state cannot authenticate a bearer. Initialization refuses to recreate version 1 when recovery history exists. [Record definitions](credential-and-recovery-records.md#human-credential-version-records) own the persisted fields.

The future CLI must verify `/v1/session` before saving a login. After bounded refresh handling, confirmed invalid credentials require removing the selected target/account's stored pair and asking for explicit sign-in. Compare the saved credential revision so another process's fresh login survives. A 403 or outage does not clear credentials. Do not automatically repeat a paid or mutating command after reauthentication.

This does not force Hydra to report a stale grant inactive. The real-provider scenario observes stale refresh and `/userinfo` independently of Inframeld rejection. These tests' direct cleanup recorder calls establish local state ordering, not production callback correctness. The separate [native worker scenarios](recovery-completion.md#implemented-execution-and-proof-backed-completion) exercise implemented native evidence delivery, durable execution and proof-backed completion, with their own qualification limits.

<a id="credential-generations-supplement-the-recovery-block"></a>

### Credential generations supplement the recovery block

[ADR-0072](../../../../docs/adr/ADR-0072-version-human-cli-credentials-across-account-recovery.md) adds identity-scoped CLI credential versions. A trusted new recovery admission atomically advances the version with its original block. The API permanently rejects earlier generations after release. Duplicate delivery and completion do not advance or reset it. Provider cleanup, original-event binding and trusted completion evidence remain mandatory.

Under [ADR-0073](../../../../docs/adr/ADR-0073-carry-explicit-authentication-evidence-in-access-contexts.md), every `AccessContextDTO` requires the actor and one complete non-secret browser-session, human OAuth or application-key evidence record. Bearer authentication retains its exact verified binding for fresh authorization checks. Both facts readers return stored principal and OAuth binding/version observations. The shared application evaluator interprets evidence and the domain policy decides currentness. The authorizers reject kind mismatches or non-current credentials before reservation or replay, following [the component boundary](eligibility-and-current-authority.md#credential-query-and-policy-boundaries). Each eligibility-input producer supplies credential currentness explicitly. These records establish no authority by themselves. Application-key evidence is currently exercised by simulated authorization callers, not a production key authenticator. [The data model](credential-and-recovery-records.md#authentication-evidence-records) owns the fields. No OAuth scope, stored operation outcome or typed binding supplies product permission. The CLI cannot choose a version. Existing public request/response schemas remain unchanged. The dedicated worker now supplies proof-backed recovery release. [Native execution tests](../../../../apps/backend/tests/integration/access/test_native_recovery_cleanup_worker.py) supplement the existing delayed production-consent tests. Host continuation and packaged-runtime qualification remain separate.

<a id="human-cli-identity"></a>

<a id="resolve-browser-and-cli-login-to-the-same-human"></a>

### Resolve browser and CLI login to the same human

Alice's Kratos browser cookie and Hydra CLI access token must ultimately resolve to the same local human principal. [ADR-0053](../../../../docs/adr/ADR-0053-use-kratos-and-hydra-for-human-cli-authentication.md) extends the authentication path, not the meaning of identity or grants. [Access](human-cli-login.md#human-cli-authentication) owns verification order and current-state checks.

| Logical value or state | Owner and constraint |
| --- | --- |
| Trusted CLI issuer/client/API audience | Operator-defined installation configuration and target binding. Never derive trust from a token or an authentication error. |
| Verified human subject | The trusted Ory integration supplies the stable Kratos identity ID. Map through the configured Kratos authority to the existing identity link, not an email or a new Hydra-named person. |
| OAuth authorization codes, grants, access/refresh token state | Hydra's isolated persistence and protocol APIs. Do not duplicate token issuance, a revocation database or permission snapshots in Inframeld's domain model. |
| Local principal, admission, active state and grants | Existing Access records, checked currently. Neither OAuth scope nor successful consent creates membership or authority. |
| CLI account binding and credential set | Local CLI settings plus a qualified OS credential store, bound to immutable target identity, API/issuer/client/audience configuration and verified account. Secrets are not backend job, trace, audit or response-cache records. |

Introspection/identity-provider response types stay at infrastructure boundaries. The application receives `AccessContextDTO` with `PrincipalId` and required non-secret authentication evidence, never a token, mutable permission cache or vendor user object. Identity lookup follows external verification without holding a database transaction across provider waits. Replacing or refreshing a CLI credential preserves principal identity. Changing trusted endpoint/issuer bindings requires fresh login rather than credential forwarding.

The implemented bearer service now reuses the same `human_identity_links` and `principals` records as browser authentication. After Hydra and Kratos verification, `PostgresHumanIdentityLinkReader` reads that exact authority/subject pair in a fresh database session. No Hydra-named person or new token table is created in Inframeld.

For example, a test provider can recognize Alice while the local test database contains no identity link for her. The session request returns 403. Requesting the `linked_human` test fixture first creates an active local principal and its link, so the same verified identity can return 200. Each test uses an isolated database, so admission from an earlier test does not carry over. [The implemented authentication boundary](credential-dispatch.md#implemented-human-authentication) links both the mocked-provider scenarios and real Hydra/Kratos tests that resolve cookie and bearer credentials to the same local principal.

The table describes ownership rather than new schema changes. Native Kratos/Hydra login, backend consent, client provisioning and provider lifecycle scenarios are implemented. The separate [recovery workflow](recovery-completion.md#implemented-execution-and-proof-backed-completion) owns implemented cleanup orchestration and its qualification limits. Account pages, protected CLI storage and first-local-admission integration remain unfinished. Incoming application-key records and their two-usable-key limit remain separate.

<a id="handle-invalidated-human-cli-credentials"></a>

### Handle invalidated human CLI credentials

[Credential versioning](#human-credential-versions) changes server-side acceptance, not HTTP schemas. An unversioned or stale human bearer receives the existing generic 401 and Bearer `invalid_token` challenge, including rejection inside current transactional authorization. Current credentials retain normal eligibility and permission failures. No version field is accepted from clients or added to session/consent responses.

The future CLI checks `/v1/session` before saving a completed login. After bounded refresh handling, confirmed invalidation clears only the selected target/account's unchanged saved credential revision and requires explicit sign-in. Permission denial and dependency unavailability retain the saved login. Authentication recovery never authorizes an automatic repeat of a paid/mutating operation.

<a id="keep-credential-invalidation-independent-of-recovery-replay"></a>

### Keep credential invalidation independent of recovery replay

[Human credential versions](#human-credential-versions) advance only when the original recovery admission is newly inserted. Its version, operation and block commit together. Repeated callbacks retain the existing version and operation. A failed transaction commits none of these effects. Independent recoveries each invalidate the previous generation, while release changes only the original checklist.

A request authenticated before recovery still carries its original binding. Both existing authorization families compare it with current state before reservation/replay. Completed operation metadata does not authorize disclosure to a stale credential. Grant fingerprints and operation identities remain unchanged.

Bulk Hydra cleanup and its independent outcomes remain required. A late grant may survive at Hydra while permanently failing Inframeld's version check. The test-controlled completion scenario does not qualify production hooks, safe evidence delivery or durable provider scheduling. Completed events must still initiate no new cleanup.

<a id="reject-a-stale-human-cli-credential-consistently"></a>

### Reject a stale human CLI credential consistently

Under [ADR-0072](../../../../docs/adr/ADR-0072-version-human-cli-credentials-across-account-recovery.md), missing/invalid binding claims or a non-current version are credential failures. Preserve the existing generic 401 problem and Bearer `invalid_token` challenge. The Access-owned handler also translates `HumanOAuthCredentialRejectedError` raised during transactional authorization, without putting HTTP types in application code or exposing versions, subjects or recovery details.

A valid credential with denied account/recovery/project permissions retains normal 403/visibility behavior. Required unavailable verification remains 503. Neither means the CLI should delete its login. Public schemas and problem codes remain unchanged.

<a id="explicit-application-key-input"></a>

## Explicit application-key input

Browser-assisted login remains the human path. When Alice deliberately configures an application account, the CLI also supports hidden application-key entry and protected automation input. Do not read a human’s saved credential as a substitute, expose the application key in process arguments or fall back between identities. Its public `ifm_app_` prefix chooses a credential family only. Full key validity and current authority remain mandatory.
