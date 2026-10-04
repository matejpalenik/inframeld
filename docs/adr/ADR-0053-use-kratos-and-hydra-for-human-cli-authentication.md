# ADR-0053: Use Kratos and Hydra for human CLI authentication

**Status:** Accepted. Partially supersedes [ADR-0012](ADR-0012-use-kratos-for-human-authentication.md) only where its browser-focused scope deferred Hydra/OAuth issuance for human CLI use. Kratos identity, browser sessions and Inframeld authorization remain selected.

**Date:** 2026-09-28. The decision was accepted during CLI design on this date and reconciled into the architecture on 2026-09-29.

## Context and Problem Statement

Alice installs the CLI and wants to sign into the same account she uses in the browser. She should not copy a session cookie, enter her password into a custom terminal authentication protocol or give a customer application her personal login. The earlier browser-only authentication scope did not provide that native-client flow.

The developer accepted browser-first human login with Kratos plus Hydra, rotating refresh tokens and strict installation/account binding. Older guides continued to describe Hydra as deferred. This record resolves that documentation discrepancy, not a missing implementation by assertion.

## Considered Options

- Kratos native/API sessions or terminal-first account interaction: considered before browser-first CLI login was selected; not the chosen CLI handoff.
- Kratos plus Hydra using standard native-client OAuth/OIDC flows: selected to retain Kratos identity while providing browser-assisted CLI authorization and token lifecycle.
- A custom cookie-to-token handoff or Inframeld-owned OAuth issuer: excluded rather than inventing a security protocol.

These summarize the recorded discussion, not a new benchmark or interoperability test.

## Decision Outcome

Use Kratos for human identities, sign-in methods and browser sessions. Use self-hosted Ory Hydra for the first-party human CLI's OAuth/OIDC flow and token lifecycle. Inframeld Access continues to own admission, active principal state, memberships, action grants and document access. OAuth scopes and consent cannot grant product permissions.

The official public client uses the system browser, Authorization Code with S256 PKCE and a temporary literal-loopback callback. It has no embedded client secret. Use maintained OAuth/OIDC libraries and Ory's documented login/consent integration, not a replacement issuer. A small account UI is required independently of the full Studio. Headless human device login remains gated on the selected OSS release's security and interoperability tests.

Human API requests use opaque access tokens privately introspected by the backend. Verify token semantics, issuer trust, audience, official client and required scope; check current Kratos identity eligibility and resolve the same existing local human principal before current authorization. Fail closed and keep application transactions outside identity-provider waits. Browser cookies retain CSRF protection. Application keys retain separate dispatch and verification, never trial-and-error fallback between credential kinds.

Keep rotating refresh tokens in secure, target/account-bound local storage with coordinated refresh. Logout and recovery use documented Ory revocation mechanisms with honest partial-failure reporting. Accepted duration defaults are deployment-configurable; a rolling refresh deadline is not an absolute session-age limit. [Access](../development/access-control.md#human-cli-authentication) owns these boundaries and the detailed client registration, login transaction, credential lifecycle and qualification requirements.

Production/network installations require HTTPS. The CLI-managed, same-machine, loopback-only trial has the narrowly defined HTTP exception in [Deployment](../development/deployment.md#managed-local-http). This is not permission for arbitrary HTTP targets, authentication bypasses or public administration ports.

Incoming application credentials remain Inframeld-issued opaque keys under ADR-0017/0018. The accepted MCP profile remains preconfigured, header-capable clients under ADR-0045. Adding Hydra for human CLI login does not add MCP OAuth discovery, third-party client onboarding, verified user delegation, machine client-credentials grants or a migration of application/provider keys into Hydra.

**Maintenance proof clarification, 2026-10-04:** reuse the transient Hydra access token from the accepted CLI login for independent candidate identity verification over protected host stdin. The CLI does not export a Kratos browser cookie. The first claim can verify before local admission through its separately authorized host operation; ordinary product requests still require admission and all current grants. [The version 1 maintenance draft](../development/access-contracts.md#maintenance-wire) defines this boundary and pending runtime qualification.

## Consequences

[ADR-0058](ADR-0058-block-product-access-during-identity-recovery-cleanup.md), accepted on 2026-10-04, clarifies the product-access block and independent provider-cleanup outcomes after verified recovery. [Accepted credential dispatch](../development/access-control.md#credential-dispatch) now selects one verifier without changing Ory token formats. Hook sequencing and pinned-release qualification remain open; existing cookie/recovery tests do not prove these extensions.

- Humans get one identity across browser and CLI, while applications retain separate least-privilege identities.
- Hydra, the login/consent UI integration, secure CLI storage, private introspection and cross-product recovery add deployment and qualification work. They are identity infrastructure beside one modular backend, not new business-domain services.
- Ory APIs supply protocol mechanisms. Inframeld still owns secure integration, admission/bootstrap and coordinated recovery; no vendor reference configuration proves our deployment is production-ready.
- Exact pinned releases/digests, credential dispatch, subject mapping, device-flow safety, local transport, rotation races and recovery behavior must pass the recorded release gates. Do not enable an unqualified flow or choose a paid distribution silently.
- Inspection on 2026-09-29 found the Kratos cookie/CSRF adapter and Kratos Compose services, not a Hydra service or CLI bearer verifier. This ADR adds no implementation, configuration, migration or runtime-test evidence and makes no claim about an independently deployed installation.

## Links

- [Client registration](../development/access-control.md#cli-client-registration), [login transaction](../development/access-control.md#cli-login-transaction), [credential lifecycle](../development/access-control.md#cli-credential-lifecycle) and [qualification](../development/access-control.md#cli-authentication-qualification): accepted detailed protocol, lifecycle and release requirements, relocated from the workshop without changing the decision.
- [Access](../development/access-control.md#human-cli-authentication), [identity records](../development/data-model.md#human-cli-identity), [HTTP contracts](../development/api-contracts.md#authentication), [Deployment](../development/deployment.md#identity-runtime), [Onboarding](../development/onboarding.md#human-login) and [MCP](../development/mcp.md#authentication): current responsibilities and limits.
- [ADR-0012](ADR-0012-use-kratos-for-human-authentication.md), [ADR-0017](ADR-0017-let-valid-application-keys-use-current-account-permissions.md), [ADR-0018](ADR-0018-use-opaque-expiring-and-revocable-application-credentials.md) and [ADR-0045](ADR-0045-support-preconfigured-mcp-clients-with-application-credentials.md): preserved identity and application-credential choices.
- External protocol references: [RFC 8252](https://www.rfc-editor.org/rfc/rfc8252.html), [OAuth security BCP](https://www.rfc-editor.org/rfc/rfc9700.html), [Ory login/consent integration](https://www.ory.com/docs/oauth2-oidc/custom-login-consent/flow), [private introspection](https://www.ory.com/docs/hydra/guides/oauth2-token-introspection) and [refresh-token handling](https://www.ory.com/docs/oauth2-oidc/refresh-token-grant). These establish mechanisms, not Inframeld runtime qualification.
