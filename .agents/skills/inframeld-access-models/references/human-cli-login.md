# Human CLI login and consent

<a id="concepts-and-owners"></a>

## Choose a focused reading task

- For consent and remembered approval, read [Human cli consent](human-cli-consent.md).

## Concepts and owners

Kratos establishes human identity through its native Hydra login integration. Hydra owns OAuth/OIDC flow state, access and refresh credentials, and remembered consent. Access owns the installation's consent checks and later product admission and permissions. The small account UI renders these flows independently of full Studio.

The public CLI client uses Authorization Code with S256 PKCE. The browser login supplies a code that the CLI exchanges for credentials. PKCE binds that exchange to the client instance that started it. Fresh state/nonce and complete issuer/response validation protect the browser round trip.

Use maintained protocol libraries, no embedded client secret, implicit/password grant or custom cookie-to-token issuer. The temporary callback binds to literal `127.0.0.1` and an ephemeral port, not the LAN. Headless device login needs separate release qualification.

<a id="recovery-retries-and-changed-identity"></a>

## Recovery, retries and changed identity

Human CLI credentials carry a server-owned version. Think of it as the generation of Alice's CLI login. A new recovery admission advances it once atomically. Duplicate delivery and block release never reset it.

Approval captures this version, checks it after browser verification and binds the grant to it. Refresh must never upgrade an old grant. Current authorization rechecks the binding before new work or replay.

An old grant can remain active at Hydra while Inframeld rejects its stale version. Existing unversioned CLI logins require fresh sign-in. Missing or changed binding evidence must not fall back to another identity. This permanent invalidation supplements the temporary recovery block and bulk cleanup. It does not prove Hydra-wide revocation or authorize production recovery completion.

Keep ordinary selected-device logout, coordinated refresh, account recovery and local credential cleanup distinct. A changed issuer or verified person cannot silently rebind a saved account. Managed same-machine loopback HTTP has its explicit deployment exception. Other installations require HTTPS. Host bootstrap uses separate host authority, not OAuth consent or a public first-signup privilege.

<a id="implementation-status-and-limits"></a>

## Implementation status and limits

The guide records implemented backend cookie/bearer verification, native consent and the separate installation client provisioner. Read-only inspection is display data, not authority for a later decision. The [recovery workflow](recovery-completion.md#implemented-execution-and-proof-backed-completion) and [protected host continuation](host-maintenance.md#recovery-cleanup-continuation) have inspected implementations. Account pages, complete CLI interaction, packaged runtime delivery and first-local-admission integration remain unfinished.

Provider tests distinguish late approvals, outstanding codes and token responses. A held HTTP request does not pause Hydra internally. Test-only token-hook denials, transport gates and staged records establish bounded observations, not a production hook, credential inventory, universal issuance fence or authority to release a block. Keep historical provider-version observations separate from current qualified results.

Before changing provider pins, read reviewed OSS versions, image digests, immutable SDK revisions, residual vulnerabilities and upgrade qualification. A latest release or passing tests is not vulnerability-free production approval.

<a id="section-use-kratoss-browser-session-flow-for-studio"></a> <a id="section-include-deployment-level-external-sign-in-in-oss-v1"></a>

<a id="alice-signs-in-through-her-company"></a>

### Alice signs in through her company

Alice completes Kratos's browser login flow. Kratos creates a secure, HTTP-only session cookie, which browser JavaScript cannot read. The backend checks it through `/sessions/whoami`, finds Alice's local principal, and checks her current Inframeld permissions.

A small account UI supplies the browser login/recovery screens and Ory's documented login/consent integration for CLI login. It displays the fields and errors supplied by Kratos and follows its cross-site request forgery (CSRF) protection. It does not require the full Studio to exist. Kratos verifies passwords. Browser product requests keep their session cookies. Adding Hydra for CLI login does not introduce Auth.js, bearer tokens in browser local storage or a native-token-to-cookie bridge.

**Optional company sign-in is included in OSS v1.** The operator configures an OpenID Connect (OIDC) provider for the installation, including its client, redirect URI, and protected secret. Kratos signs Alice in through that provider and creates its own session. A local installation still requires authentication, but does not require a company provider or cloud identity account.

Alice can connect more than one sign-in method to the same account. Suppose she already uses a password and later selects company sign-in with the same email address. She must first prove access to her existing account using an attached method, such as that password. Matching email addresses alone do not authorize linking. Once linked, either method identifies the same Alice and uses her existing Inframeld permissions. She does not repeat the linking step on each login or gain a second local account.

Kratos maintains these links. Inframeld identifies its verified Kratos identity by **authority + subject**, meaning the identity source and the account ID within it. Email is not the identity key. Company login does not make Alice an administrator, and a token from her company is not automatically an Inframeld API credential. Importing company group memberships would need a separately designed policy.

Kratos's browser-session flow does not itself require Hydra. **Hydra is nevertheless selected for human CLI login**, not deferred installation-wide. General third-party OAuth onboarding, arbitrary token exchange and verified user delegation remain outside this scope. The distinct accepted CLI flow follows below.

If a session is invalid, expired, or cannot be verified, Inframeld denies the request. It does not continue when Kratos is unavailable. Browser logout rejection and disabled/expired session handling have backend coverage described in [credential dispatch](credential-dispatch.md).

The required standalone account UI still needs integration and testing for logout, recovery completion, password settings and configured multi-factor authentication (MFA) challenges. These are account-UI work, not deferred Studio features. Supporting a configured challenge does not make MFA mandatory or select a new factor. Secure first-administrator setup and email delivery also need their deployment integration and tests. Hydra integration owns backend verification and recovery cleanup. Displaying a completed form does not prove admission or cleanup succeeded.

<a id="human-cli-authentication"></a>

<a id="alice-signs-into-the-cli-with-the-same-human-identity"></a>

### Alice signs into the CLI with the same human identity

Alice runs an explicit `login` or the guided setup login step. The system browser shows the installation and human account she is approving. Hydra delegates login to the Ory account UI integrated with Kratos. The CLI receives protocol credentials, not Alice's password or browser cookie. Access then resolves the same local human principal used by browser requests.

The complete browser-to-CLI login journey is **accepted design with runtime qualification still ahead**. The backend already implements cookie and human bearer verification on the session and project-grant routes. The [implemented boundary](credential-dispatch.md#implemented-human-authentication) explains that code and its test coverage. The [client registration](#cli-client-registration), [login transaction](human-cli-credential-lifecycle.md#cli-login-transaction), [credential lifecycle](human-cli-credential-lifecycle.md#cli-credential-lifecycle) and [qualification requirements](human-cli-credential-lifecycle.md#cli-authentication-qualification) cover the remaining delivery profile. Terminal examples illustrate the experience. They do not establish unpublished HTTP schemas.

| Caller | Credential and verifier | What it does not grant |
| --- | --- | --- |
| Human browser | Kratos session cookie, verified through Kratos. Preserve CSRF on cookie-authenticated writes. | CLI tokens, application-key issuance or product permissions by sign-in alone. |
| Human CLI | Opaque Hydra access token, verified privately. Current Kratos identity eligibility and local human state. | Application identity, third-party delegation or authority derived from OAuth scopes. |
| Application HTTP/MCP client | Inframeld-issued opaque application key, verified against its stored verifier and restrictions. | Human-only administration or acceptance on an unapproved audience/adapter. |

Follow the CLI request in execution order:

1. Resolve the trusted installation/issuer and official public client. Use maintained OAuth/OIDC libraries for Authorization Code with S256 PKCE, fresh state/nonce and complete response/issuer validation. No embedded client secret or implicit/password grant. A temporary callback binds to literal `127.0.0.1` and an ephemeral port, never the LAN. Headless device authorization needs its separate qualified release path.
2. Use Ory's documented login/consent integration with Kratos, showing the verified account and requested installation access. Bind the returned credentials to that exact target configuration and human. Login does not silently select a different account, target or project. Operator bootstrap and product admission remain separate checks.
3. On each API request, privately introspect the opaque access token against configured Hydra. Require active/unexpired access-token semantics, the canonical API audience, official CLI client and required API scope. Reject ID/refresh tokens and caller-supplied verification destinations. An active result alone is insufficient.
4. Check the corresponding Kratos identity is currently eligible. Resolve the trusted stable Kratos identity ID to the existing authority/subject link, then the admitted active human principal. Do not create a second person from Hydra's issuer, merge by email or add grants. No positive introspection/eligibility cache is selected for v1.
5. Return the authenticated actor and non-secret CLI credential binding and run the operation's current project/action/document checks. External identity calls precede the short application lookup transaction. Never hold a transaction while waiting for Hydra or Kratos. Verification failure/unavailability denies execution without falling back to another identity.

Reject competing credential mechanisms instead of trying cookies, OAuth tokens and application keys until one succeeds. The [HTTP dispatch contract](credential-dispatch.md#credential-dispatch) defines which path may verify each credential. The implemented human routes follow it without trying another verifier after a failure. No application credential becomes a human token merely because both travel in an Authorization header. No human CLI token automatically becomes an MCP credential.

Inframeld application keys reserve the `ifm_app_` prefix. Ory token formats remain unchanged. [Application-key recognition](application-key-contracts.md#application-key-contract), [complete syntax and verification](application-key-contracts.md#application-key-contract), and [authentication errors](../../../../docs/development/error-handling.md#authentication-contract) record the accepted choices. Human verification adapters exist. Application-key verification and the complete Ory runtime still need implementation or qualification.

<a id="cli-client-registration"></a>

<a id="register-one-first-party-public-client"></a>

### Register one first-party public client

Alice signs into local and dev with the same CLI executable. Each installation independently provisions `inframeld-cli` through Hydra's private administration interface. An ordinary user neither registers a client nor receives an administrator credential. A **public client** cannot keep a shared secret inside its executable. Public does not mean that its users receive public access to data.

| Setting | Accepted contract |
| --- | --- |
| Client authentication | `token_endpoint_auth_method=none`. No embedded client secret |
| Desktop grants and response | `authorization_code`, `refresh_token`. Response type `code`, not implicit/hybrid token delivery |
| PKCE | S256 required by server policy and used by the CLI. Reject missing, plain or incorrect proof |
| Scopes | `openid`, `offline_access`, `inframeld:api` |
| API audience | Installation's explicitly configured canonical API URL, matched exactly |
| Subject | Actual stable Kratos identity ID through the trusted integration. No pairwise remapping for this first-party client |
| Access token | Opaque. Intended only for this installation's API |
| Desktop callback | `http://127.0.0.1:<ephemeral-port>/oauth/callback`. Fixed host/path with standard ephemeral-port variation only |
| Consent | Show account, installation and requested access. Recognizing the client ID alone never skips approval |
| Device grant | Enable only after qualification of the selected OSS release |
| Excluded grants | Password, client credentials, arbitrary token exchange and delegated-user grants |

An **issuer** identifies the trusted Hydra installation. An **audience** identifies the API a token is for. Neither is a project selector. `offline_access` permits refresh, not unattended administration. Do not put current project or document grants into tokens. ID tokens describe authentication to the CLI, refresh tokens go only to Hydra, and only access tokens go to the business API.

The implemented [`HumanOAuthClientProvisioner`](../../../../apps/backend/src/inframeld_backend/access/application/protocols/human_oauth_client_provisioner.py) reconciles this fixed profile through the official Hydra SDK. The separate `python -m inframeld_backend.provision_oauth_client` setup command creates a missing client, updates managed drift in place or reports an unchanged registration after reading it back. It preserves display metadata, unrelated clients and independent login chains. It removes client-specific lifetime overrides so [native server settings](human-cli-credential-lifecycle.md#provider-lifetime-configuration) remain authoritative. It never deletes and recreates the client or runs during API startup.

Register `http://127.0.0.1/oauth/callback` without a port. Hydra permits the native-client ephemeral-port variation at authorization, while code exchange must use the exact URI from that attempt. The [production provisioner scenarios](../../../../apps/backend/tests/integration/access/test_hydra_cli_provisioning.py) qualify both rules against the pinned provider.

The host-authorized command needs only focused Hydra/lifetime configuration and private administration access, not an application database or fingerprint key. Bounded readiness reads may repeat. Mutations do not automatically retry. Stopping and write admission are synchronized: stopping first prevents mutation, while an admitted write may still dispatch or finish late. A timeout after admission reports an unknown outcome. Cancellation propagates without promising that no write occurred. A later explicit invocation reconciles the actual registration. [Local setup](../../../../docs/development/getting-started/local-setup.md#configure-the-cli-client) gives the development command and UI boundary. This does not implement the Rust CLI, account pages or packaged runtime.

Target registration obtains the expected issuer/client/audience through validated one-server-URL discovery. Do not infer an issuer from the API hostname or replace it from an authentication error. Standard discovery must return exactly the expected issuer. Do not send existing credentials during discovery or forward credentials across origin-changing redirects.

Credential binding includes immutable target identity, API URL, issuer, client, audience, managed-installation identity where applicable, and verified human identity. Renaming a target label preserves that binding. Changing a bound endpoint/issuer/client/audience/installation invalidates every affected saved login and requires fresh login. Equal URLs, email addresses or aliases do not authorize sharing credentials between targets. Only the separately verified managed-local runtime gets the [bounded HTTP exception](../../inframeld-application-contracts/references/cli-local-runtime.md#managed-local-http). Manually registered HTTP targets do not.

<a id="sources-and-rationale"></a>

## Sources and rationale

- [ADR-0012](../../../../docs/adr/ADR-0012-use-kratos-for-human-authentication.md) records the earlier browser-focused choice. ADR-0053 partially supersedes its Hydra deferral while retaining Kratos identity and Inframeld authorization.
- [Human CLI flow](#human-cli-authentication), [registered client](#cli-client-registration), [credential lifecycle](human-cli-credential-lifecycle.md#cli-credential-lifecycle) and [qualification](human-cli-credential-lifecycle.md#cli-authentication-qualification).
- [Native consent](human-cli-consent.md#native-hydra-consent), [credential versions](human-cli-credential-lifecycle.md#human-credential-versions), [browser API](human-cli-consent.md#human-oauth-consent) and [implemented chain](human-cli-consent.md#human-oauth-consent).
- [CLI identity records](human-cli-credential-lifecycle.md#human-cli-identity), [version records](credential-and-recovery-records.md#human-credential-version-records), [ADR-0053](../../../../docs/adr/ADR-0053-use-kratos-and-hydra-for-human-cli-authentication.md), [ADR-0071](../../../../docs/adr/ADR-0071-use-native-kratos-login-and-checked-hydra-consent.md) and [ADR-0072](../../../../docs/adr/ADR-0072-version-human-cli-credentials-across-account-recovery.md).
- [Deployment identity runtime](../../inframeld-architecture/references/runtime-deployment-and-storage.md#identity-runtime), [host bootstrap](../../inframeld-architecture/references/first-use-and-private-defaults.md#host-bootstrap), [HTTP ordering](recovery-provider-cleanup.md#hydra-issuance-evidence), [provider review](../../inframeld-architecture/references/runtime-deployment-and-storage.md) and [upgrade evidence](authorization.md).

The first-party discovery profile is accepted through [ADR-0098](../../../../docs/adr/ADR-0098-publish-bounded-first-party-discovery.md). Its [owning workflow](../../inframeld-application-contracts/references/cli-targets-and-accounts.md#target-discovery) distinguishes the implemented stateless boundary from future saved targets and full login.
