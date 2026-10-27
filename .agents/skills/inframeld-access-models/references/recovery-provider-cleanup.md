# Confirm provider cleanup without guessing

Alice resets her password while a CLI refresh is already in flight. Native Kratos cleanup and Hydra cleanup are separate obligations. A successful call, callback or local version check cannot establish every provider outcome.

<a id="bulk-hydra-cleanup"></a>

## Follow provider cleanup

1. Establish the original subject's trusted installation/provider binding from the admitted flow.
2. Run the bounded native Kratos cleanup while preserving the legitimate recovery session. Track trusted confirmation independently.
3. Revoke the subject's CLI grants and forget its remembered Hydra logins through the two separate bulk capabilities below. Acknowledging one call does not confirm every obligation.
4. Reconcile unfinished outcomes under the original durable obligation. Do not start cleanup for an already-completed event or guess success from an empty consent listing.

Use bulk subject cleanup, not a frozen per-login inventory or timestamp cutoff. Ordinary selected-device logout has narrower scope. Provider calls remain outside SQL transactions.

<a id="delayed-requests-and-failures"></a>

## Delayed requests and failures

An unfinished retry or an already dispatched cleanup call may invalidate newer CLI credentials. Report that possibility honestly. A durably completed event must not initiate new cleanup. Original obligations survive interruption and use the existing bounded reconciliation contract.

The accepted [workflow retry budget](recovery-completion.md#hydra-cleanup-retry-budget) limits automatic attempts in each run for the original operation. An additional run needs [fresh explicit host authorization](recovery-completion.md#operator-cleanup-continuation), retaining earlier history and confirmed progress. Individual revoker calls retain their explicit finite deadlines and disabled SDK retries. A run's one-hour window does not extend a call's timeout or make an uncertain response confirmed. It also cannot recall calls dispatched by an earlier run. The [dedicated recovery worker](recovery-completion.md#implemented-execution-and-proof-backed-completion) implements scheduling and durable budget enforcement for this workflow.

[Failure handling](recovery-completion.md#hydra-cleanup-failure-handling) retries recoverable provider failures and uncertain bulk outcomes within budget, but ends the run early for a known permanent rejection. The adapter's confirmed/failed/uncertain observation does not by itself supply the complete retry decision. In particular, failed cleanup evidence must not automatically be interpreted as a permanent error. The implemented application-owned outcome/disposition result follows the [accepted exact mapping](recovery-completion.md#hydra-cleanup-failure-handling). The worker interprets that disposition within the stored budget. Unexpected programming errors stop the run rather than becoming automatic retries.

A login approval or refresh can cross the cleanup calls. HTTP-ordering tests distinguish outstanding authorization codes, prepared approvals, late token responses and approval between bulk calls. A held request or response does not freeze Hydra internally. Staged records are test evidence, not a credential inventory or authority to release a block.

The durable credential version supplements bulk cleanup. A late grant may remain accepted at Hydra and still receive Inframeld's invalid-token response. Refresh descendants keep the old version. Current Inframeld rejection does not establish Hydra-wide rejection or complete provider cleanup.

Pinned Kratos observations also distinguish recovery-code acceptance from password replacement. Accepting the recovery code leaves the old password usable until replacement. Settings pre-save and post-save failures have different persistence effects. A recovery-created settings flow preserves original-flow evidence, while a fresh settings flow cannot claim it through a query parameter.

<a id="documented-native-hook-support"></a>

## Documented native-hook support

**Documentation and source inspected on 2026-10-25, no new runtime checks.** [ADR-0081](../../../../docs/adr/ADR-0081-use-native-kratos-hooks-for-recovery-evidence.md) accepts native hooks plus durable reconciliation. The [private handoff](private-recovery-handoff.md#native-hook-evidence) owns the selected sequence. Current Ory pages also describe Ory Network, so the pinned OSS source establishes availability in our selected release.

- [Ory's hook documentation](https://www.ory.com/docs/kratos/hooks/configure-hooks) lists recovery and password-settings hooks. Its [webhook guide](https://www.ory.com/docs/guides/integrate-with-ory-cloud-through-webhooks) documents configurable payloads and API-key authentication. These are integration capabilities, not a combined recovery-completion certificate.
- The [Kratos v26.2.0 webhook implementation](https://github.com/ory/kratos/blob/v26.2.0/selfservice/hook/web_hook.go#L247-L277) places a settings webhook after persistence when `can_interrupt` and `response.parse` are false. Keeping `response.ignore` false makes it wait for the callback response. Its recovery hook supplies flow and identity but omits the session. Both settings update stages supply the session. The settings creation pre-hook also supplies the session, but not a separate identity object. Its identity comes from the native session.
- The [settings executor](https://github.com/ory/kratos/blob/v26.2.0/selfservice/flow/settings/hook.go#L206-L269) persists the password change before its post-persistence hook loop. It stops on a hook error. A callback ordered after native revocation is therefore not reached through that loop when revocation fails. The [native revoker](https://github.com/ory/kratos/blob/v26.2.0/selfservice/hook/session_destroyer.go#L50-L56) excludes the session used for the change, consistent with [Ory's session-revocation documentation](https://www.ory.com/docs/actions/revoke-active-sessions).
- The [settings handler](https://github.com/ory/kratos/blob/v26.2.0/selfservice/flow/settings/handler.go) runs its creation pre-hook before saving the new flow. The [code-recovery strategy](https://github.com/ory/kratos/blob/v26.2.0/selfservice/strategy/code/strategy_recovery.go) calls that creation path with its activated recovery session after the recovery hook. Restarted flows must use the durable session association. Do not assume a restarted creation hook already contains the old request URL, which the handler copies afterward.
- [Hydra's pinned API contracts](https://github.com/ory/hydra/blob/v26.2.0/consent/handler.go#L58-L288) provide subject/client grant revocation and separate subject-wide remembered-login deletion. Inframeld calls these APIs. It does not wait for a Hydra password-recovery event or use token-customization hooks as cleanup evidence.

This source inspection supports the chosen hook placement. It does not deliver callbacks durably, validate their original-flow association or make the provider sequence atomic with Inframeld. Earlier real-provider observations below remain separate evidence. Those contracts are [resolved by ADR-0085](decision-recovery-production-completion.md). The later [private delivery](private-recovery-handoff.md#implemented-private-delivery) and [completion](recovery-completion.md#implemented-execution-and-proof-backed-completion) references describe their inspected implementations and separate behavioral tests.

<a id="kratos-password-reset-evidence"></a>

<a id="observed-kratos-password-reset-boundaries"></a>

#### Observed Kratos password-reset boundaries

Alice enters a valid recovery code and receives a session for changing her password. Her old browser session is revoked, but her old password still works for a new login until she saves a replacement. The [real Kratos tests](../../../../apps/backend/tests/integration/kratos/test_kratos_password_reset_hooks.py) exercise this interval on **Kratos v26.2.0**, following the original v25.4.0 qualification. Code verification and successful password replacement are separate events. Production integration must keep the recovery obligation effective across that interval.

The test-only password-settings configuration runs an interrupting webhook before password persistence, native `revoke_active_sessions` after persistence, then a non-interrupting webhook that waits for its response. These are settings-specific test observations, separate from the production recovery envelope.

The separate recovery probe in [the test configuration](../../../../config/kratos/test.yaml) also has a callback named `complete`. It runs during code recovery, before password replacement. That name is not password-completion evidence and must not be copied as the production release boundary. The selected later signal is the post-persistence password-settings webhook.

| Observed boundary | Password and session behavior |
| --- | --- |
| Before-save hook is paused | The old password still works and the replacement fails. A new login can establish another session. |
| After-save hook is paused | The replacement works and the old password fails. Native cleanup has revoked the intervening session while preserving the session used to change the password. |
| Before-save hook rejects | Kratos returns 400. The old password and intervening session remain valid, with no after-save callback. |
| After-save hook rejects | Kratos returns 502, but the replacement password and completed native revocation remain effective. The legitimate recovery session stays valid. |
| Password validation rejects weak input | Kratos returns 400 before either settings callback runs. |

For the settings flow created directly by recovery, the stored initial request URL retains the original recovery flow ID. Both settings hooks can report that ID, while their own settings flow ID is different. On v26.2.0, both hooks supply the same session ID observed by the recovering browser. The earlier v25.4.0 qualification found no session in the pre-save hook. This added pre-save identifier does not establish that the new password was persisted or that native cleanup ran. The narrow test templates extract only the single `flow` value from the exact private recovery endpoint, and never transmit the URL, passwords, cookies or tokens. A fresh settings flow started with a caller-supplied `flow` query parameter reports no recovery association, even on the same session. These observations match the pinned [code-recovery strategy](https://github.com/ory/kratos/blob/v26.2.0/selfservice/strategy/code/strategy_recovery.go) and [settings hook implementation](https://github.com/ory/kratos/blob/v26.2.0/selfservice/hook/web_hook.go).

This identifies usable correlation evidence, not a production validator. Production integration must check the original registered operation, identity and installation/provider binding, qualify separately restarted settings flows, and reconcile lost responses safely. The in-memory probe does not persist obligations or block product access. The later [private delivery](private-recovery-handoff.md#implemented-private-delivery) and [completion workflow](recovery-completion.md#implemented-execution-and-proof-backed-completion) implement durable callbacks and cleanup reconciliation. Their tests remain separate from these probe observations. [Bulk Hydra cleanup calls](recovery-provider-cleanup.md#hydra-cleanup-evidence) are qualified separately. The historical five-field draft is superseded by [the version 2 private evidence contract](private-recovery-handoff.md#recovery-wire). This specification adds no runtime provider-test evidence.

<a id="standalone-provider-cleanup-boundary"></a> <a id="provider-revocation"></a>

<a id="bulk-provider-cleanup-for-recovery"></a>

### Bulk provider cleanup for recovery

Alice resets her password. The [revocation capability](../../../../apps/backend/src/inframeld_backend/access/application/protocols/human_oauth_credential_revoker.py) accepts her verified provider subject, rather than individual login IDs or a business Command. Its [Hydra adapter](../../../../apps/backend/src/inframeld_backend/access/infrastructure/revokers/hydra_human_oauth_credential_revoker.py) makes separate calls to revoke her `inframeld-cli` token grants and forget all her Hydra remembered logins. The latter operation has no client filter. Neither call changes Bob's credentials or revokes Kratos browser sessions.

The application must establish the subject's provider and installation binding before calling. The adapter opens no database transaction, persists no checklist and releases no access block. Each call has an explicit finite positive deadline. The injected SDK client has retries and debug logging disabled, and its caller owns the pool. Errors expose no provider body or credentials.

A timeout or cancellation does not stop the SDK thread or establish its remote result. Under [ADR-0070](../../../../docs/adr/ADR-0070-use-bulk-hydra-revocation-for-identity-recovery.md), a delayed call or unfinished retry may invalidate newer Alice credentials. A durably completed event must not initiate another cleanup. Ordinary selected-device logout keeps its narrower scope. Follow [the provider evidence](recovery-provider-cleanup.md#hydra-cleanup-evidence) for verified behavior and [the completion workflow](recovery-completion.md#implemented-execution-and-proof-backed-completion) for durable orchestration and its qualification limits. One successful bulk call is not confirmation of the whole recovery.

<a id="production-qualification-boundary"></a>

## Production qualification boundary

The local recovery aggregate, repository and completion service exist. The native-hook approach is accepted in ADR-0081. Real-provider fixtures can observe ordering and extract evidence, but test-only extraction is not trusted production evidence. Private native callbacks, durable provider orchestration, proof reconciliation and [protected host continuation](host-maintenance.md#recovery-cleanup-continuation) have inspected implementations. Concurrent first-local-admission integration remains unfinished. An acknowledgment alone cannot establish cleanup success. Follow the resolved [PD-ACCESS-03 contract and runtime acceptance matrix](decision-recovery-production-completion.md) for production completion and [the accepted PD-ACCESS-04 identity workflow](identity-admission-coordination.md) for local coordination. The shared identity lock is implemented for local recovery and initialization. These status corrections supply no new provider-cleanup evidence and do not implement first local admission.

Bulk Hydra cleanup can affect credentials issued during an unfinished recovery. A completed duplicate starts no new cleanup. Kratos recovery/password-reset ordering and native completion must be verified for the deployed version. A stale provider login cookie can require reauthentication. Permanent credential versions protect Inframeld even when a delayed provider grant completes. These limitations remain separate from successful local checklist persistence.

<a id="what-the-new-provider-observations-establish"></a>

#### What the new provider observations establish

The [native integration scenarios](../../../../apps/backend/tests/integration/access/test_native_hydra_consent.py) drive real Kratos password login and the production consent API. They cover unadmitted identities, remembered consent and its unchanged original duration, explicit denial, current browser/identity/recovery rejection and delayed approval. The existing direct-admin harness remains separately qualified for its original cases.

There is a real gap between checking recovery and completing external approval. A delayed approval resumed after CLI-grant deletion but before remembered-login deletion can issue working credentials. Forgetting remembered logins afterward does not revoke those new grants. The versioned test now releases the original checklist through the test-controlled local completion service and verifies that the late grant still receives product `401 http_error`. Its refreshed descendant keeps the old version and is also rejected. Hydra can still report it active and answer `/userinfo`, while a fresh native login receives a working current generation. These direct test outcomes do not qualify production cleanup callbacks. A prepared continuation resumed after both calls, with the revoked remembered cookie still present, instead returns the pinned OAuth category `error` without a code. That particular rejection is not a universal recovery fence and is not silently retried.

The private [test-only token hook](../../../../apps/backend/tests/support/hydra_token_hook.py) pauses one selected request after Hydra has validated/read its credentials, before response persistence. Code exchanges, including skipped-consent codes, crossing cleanup return `500 server_error`. Refresh crossing cleanup returns `400 invalid_request`. Neither response contains access or refresh credentials. Bob's credentials remain usable and Alice can obtain fresh credentials afterward. These fixed observations differ from the earlier HTTP-before-dispatch `invalid_grant` cases.

The hook does not pause inside a database commit or qualify every internal race. Its observation records contain only the selected subject, client, grant type and arrival count. Gates use ten-second deadlines inside thirty-second scenarios, with five-second test HTTP requests. It is configured only in the private test stack and adds no production policy layer. These token-hook observations alone supply no completion authority. The implemented [completion proof](recovery-completion.md#completion-proof) also requires durable native evidence, both saved Hydra confirmations and current local checks.

<a id="hydra-cleanup-evidence"></a>

<a id="bulk-revoke-a-recovering-humans-cli-credentials"></a>

#### Bulk revoke a recovering human's CLI credentials

Alice resets her password. The [revocation Protocol](../../../../apps/backend/src/inframeld_backend/access/application/protocols/human_oauth_credential_revoker.py) and standalone [Hydra adapter](../../../../apps/backend/src/inframeld_backend/access/infrastructure/revokers/hydra_human_oauth_credential_revoker.py) accept her trusted provider subject. They need no list of her individual grants or remembered logins. Bob's credentials remain unaffected.

| Operation | Scope and tested effect on Hydra v26.2.0 |
| --- | --- |
| `revoke_cli_grants()` | Alice plus the fixed `inframeld-cli` client. Access tokens become inactive and refresh is denied, including rotated descendants and skipped-consent grants. Other-client grants and remembered logins remain valid. |
| `revoke_remembered_logins()` | All of Alice's Hydra remembered logins, across clients. Browsers can no longer skip Hydra authentication. Issued tokens remain valid and need the separate grant call. This subject-wide API sends no front-channel or back-channel logout notifications. |
| Repeat an unfinished bulk request | Newer Alice credentials may be invalidated too. Bob remains unaffected, and Alice can authenticate again after cleanup finishes. |

[The bulk provider tests](../../../../apps/backend/tests/integration/access/test_hydra_credential_cleanup.py) cover independent browsers, grants sharing a remembered login, rotated refresh descendants, client isolation and empty scopes. They simulate acknowledgement loss after a real deletion, then verify the effect of retrying after Alice obtains newer credentials. Forgetting remembered logins and invalidating tokens are independent operations. An empty-scope acknowledgement establishes no account identity or local admission.

**Pinned reauthentication edge:** if Alice's browser still carries a revoked remembered-login cookie and the new login is not remembered, Hydra v26.2.0 rejects that first attempt with OAuth error category `error`. Its response clears the stale cookie, and a second explicit attempt in the same browser succeeds without remembering the login. [The provider test](../../../../apps/backend/tests/integration/access/test_hydra_credential_cleanup.py) retains this case. It matches the [authentication strategy](https://github.com/ory/hydra/blob/v26.2.0/consent/strategy_default.go#L433), which clears the old cookie before deleting its already-removed session. The helper validates the error callback's original state, reports only that allowlisted category and adds no automatic retry. Production account-UI handling remains to qualify.

Every call requires a finite positive deadline. The caller owns the official SDK client and pool, with retries and debug logging disabled. An expected empty HTTP 204 confirms that individual request. Explicit 4xx responses are failed evidence, including 404. Transport/server errors, timeouts and unexpected responses are uncertain. The adapter returns no provider body or credentials and retries nothing. Cancellation propagates. The blocking SDK thread can still finish after its caller times out or cancels.

[ADR-0070](../../../../docs/adr/ADR-0070-use-bulk-hydra-revocation-for-identity-recovery.md) accepts this simpler recovery policy. A durably completed event must not initiate another cleanup, but deduplication cannot recall a request already dispatched. The legitimate Kratos recovery browser session stays protected, and ordinary selected-device CLI logout retains its narrower scope.

The pinned [handlers](https://github.com/ory/hydra/blob/v26.2.0/consent/handler.go) distinguish subject/client grant deletion from subject-wide remembered-login deletion. [Bulk persistence](https://github.com/ory/hydra/blob/v26.2.0/persistence/sql/persister_consent.go) does not use the consent listing's skipped-flow or expiry filter. The caller must first establish the subject's original provider and installation binding. A typed subject and one successful request do not establish complete recovery cleanup or authorize release. Private callbacks, dedicated execution and proof-backed completion are implemented. Their [owning workflow](recovery-completion.md#implemented-execution-and-proof-backed-completion) distinguishes current-version rejection from Hydra-wide revocation.

<a id="hydra-issuance-evidence"></a>

<a id="when-login-or-refresh-crosses-cleanup"></a>

#### When login or refresh crosses cleanup

Alice starts signing in to the CLI, then recovery cleanup runs before her login finishes. The result depends on which step Hydra has reached. [Seven real-provider cases](../../../../apps/backend/tests/integration/access/test_hydra_issuance_cleanup_ordering.py), verified against Hydra v26.2.0 on 2026-10-24, separate these orderings.

| Ordering | Observed result |
| --- | --- |
| Start authorization, finish both bulk calls, then approve login and consent | Alice receives working credentials. The test helper verified Kratos before the pause and deliberately does not recheck it before approving. Earlier cleanup cannot prevent a later approval from issuing new credentials. |
| Issue a code, revoke CLI grants, then exchange the code | Hydra returns `invalid_grant` without tokens. Both ordinary and skipped-consent codes are covered. |
| Complete code exchange, hold its successful response, run cleanup, then deliver the response | The helper receives the earlier success, but its access token is already inactive and refresh is denied. A late response cannot restore the deleted grant. |
| Hold a refresh request before dispatch, run cleanup, then send it | Hydra rejects refresh with `invalid_grant`. The request had not reached Hydra during cleanup. |
| Complete refresh, hold its successful response, run cleanup, then deliver it | The rotated credentials are already inactive and cannot refresh. |
| Start a fresh login after cleanup finishes | Alice receives working credentials again. Bob's access, refresh and remembered login remain usable in every ordering. |

The outstanding-code result verifies [Ory's documented revocation behavior](https://www.ory.com/docs/oauth2-oidc/revoke-consent) against the pinned release. The staged [provider helper](../../../../apps/backend/tests/support/hydra_provider.py) retains `issue_tokens()` for existing callers. Its pending-login and code records protect secrets in representations and exist only for tests. The harness approves challenges through private APIs, without implementing the production account UI.

The test-only [transport gate](../../../../apps/backend/tests/support/hydra_token_request_gate.py) pauses one explicitly armed token request. Its after-response mode reads and closes the complete real response before signalling the test. Events establish ordering without sleeps. HTTP calls have five-second timeouts, bulk calls use three-second deadlines, gates have ten-second deadlines and each scenario has a thirty-second deadline. Request tasks are cancelled and awaited on failure before their transport closes. Neither helper retries a failure silently.

These tests control HTTP boundaries, not Hydra's internal processing. They do not prove every interleaving between issuance and deletion inside the provider. Successful bulk responses alone therefore do not establish safe recovery completion without trusted Kratos evidence, durable version invalidation and current local release checks. The [native consent checks](human-cli-consent.md#native-hydra-consent) and a test-only token hook now add evidence at narrower boundaries. Durable execution and proof-backed block release are implemented. Requests already processing can still finish late, with old-version credentials rejected by Inframeld.

<a id="hydra-discovery-evidence"></a>

<a id="consent-listing-is-observation-not-cleanup-evidence"></a>

#### Consent listing is observation, not cleanup evidence

Alice can have working credentials that the consent listing does not show. [Small real-provider scenarios](../../../../apps/backend/tests/integration/access/test_hydra_cleanup_target_discovery.py) retain that finding while qualifying bulk cleanup without selecting targets from listed rows.

| Tested case | Observation and bulk behavior |
| --- | --- |
| Remember consent, then authorize with consent skipped | The listing shows one row while the skipped flow has working credentials. Subject/client bulk cleanup invalidates both flows and denies refresh. |
| Remember login, then decline consent | The listing is empty while the browser can skip authentication. Subject-wide remembered-login cleanup removes that ability. |
| Remove the last listed grant | The listing becomes empty, but remembered authentication remains until its separate cleanup call. |
| Issue CLI credentials during the old-password interval | Kratos password replacement invalidates the intervening browser session while earlier and intervening Hydra tokens remain active in this setup. Bulk cleanup removes them and a later legitimate CLI grant. The recovery browser session remains valid, and a fresh CLI login works afterward. |
| Unknown subject | An empty listing establishes no identity or permission. |

The listing observation is private to this test module. One five-second HTTP request reads at most ten fixture rows and rejects an unexpected next page. It returns only a count, never a cleanup inventory. No production code uses the listing, and no target capture, pagination utility, original-target snapshot or timestamp cutoff remains in the recovery capability.

The direct-admin harness verifies Kratos identities and approves Hydra challenges through private test APIs. That path does not implement the account UI, bind provider-session IDs or configure logout receivers. Its separate [native-login path](human-cli-consent.md#native-hydra-consent) now exercises Kratos-owned login and the production consent API. These tests establish the listed boundaries in this setup. [Separate issuance tests](recovery-provider-cleanup.md#hydra-issuance-evidence) now qualify controlled HTTP ordering around code exchange and refresh. Private callback delivery and durable scheduling are implemented. Protected host continuation remains separate. [The accepted completion proof](recovery-completion.md#completion-proof) scopes late-issuance protection to permanent Inframeld rejection of old versions. It does not require proving Hydra-wide inactivity or claim every provider-internal race is qualified.

### Native delivery boundary

The [production callback qualification](private-recovery-handoff.md#implemented-private-delivery) uses real native hooks and the private application, separately from the older in-memory probe observations above. It establishes durable Kratos evidence and no Hydra confirmation or block release. The separate [native worker tests](../../../../apps/backend/tests/integration/access/test_native_recovery_cleanup_worker.py) now join that evidence to real provider cleanup and checked release.
