# ADR-0071: Use native Kratos login and checked Hydra consent

**Status:** Accepted. Supplemented by [ADR-0072](ADR-0072-version-human-cli-credentials-across-account-recovery.md) for permanent Inframeld rejection of stale CLI generations

**Date:** 2026-10-24

## Context and Problem Statement

Alice signs in to the CLI through her browser. Kratos must establish who she is, while Inframeld decides whether this CLI may request this installation's API access. Reimplementing password verification or login approval would duplicate Kratos's existing Hydra integration.

Recovery adds another boundary. Alice's old browser must not approve CLI access while her cleanup is pending. A check can still become stale while a provider call is underway, so checking recovery before approval does not by itself authorize later recovery completion.

## Considered Options

- Implement an Inframeld login-approval service alongside Kratos. This gives more application control but duplicates an integration already supplied by the pinned provider.
- Use native Kratos login and an Inframeld consent service. This keeps identity verification with Kratos and installation policy with Access.
- Require approval on every explicit CLI login. This is simpler, but the developer selected Hydra's native remembered approval with a bounded lifetime.

## Decision Outcome

Use Kratos's `oauth2_provider.url` integration for Hydra login. Kratos supplies the verified subject and provider session binding. Inframeld does not accept passwords or independently approve login through a competing service.

Access owns the cookie-only consent service and API. Every inspection and decision freshly reads Hydra's request. Only `inframeld-cli`, supported scopes and the exact configured API audience are eligible. Supported requests verify the current Kratos browser identity and exact subject, then check recovery state. No local account is created or required for OAuth consent. Product admission and project permissions remain separate.

Allow users to remember an explicit approval through Hydra. The operator-configurable positive whole duration defaults to one hour. A provider-reported remembered approval still receives current checks, and automatic continuation must not extend its lifetime. Client-wide automatic consent is not a substitute for the user's approval.

The [browser API contract](../../.agents/skills/inframeld-access-models/references/human-cli-consent.md#human-oauth-consent) owns inputs, outputs and failure behavior. Provider calls run outside SQL transactions with finite deadlines and no automatic retries. A timed-out approval may still finish remotely. The service returns only a checked continuation to the configured public Hydra authorization endpoint.

## Consequences

The account UI can render Ory forms and consent details without becoming another authentication or policy implementation. It must preserve the matching browser context and follow the returned Hydra continuation. Native login, backend consent and the separate client setup command have distinct lifecycles. Delivering the account pages and Rust CLI remains separate work.

Consent is external work, not an aggregate mutation needing an artificial entity or an application idempotency reservation. Hydra owns its flow state and final one-use verifier handling. An inspection result is display data, not an authorization certificate for a later decision.

Recovery remains blocked until its own independently qualified workflow can finish safely. The [issuance observations](../../.agents/skills/inframeld-access-models/references/human-cli-consent.md#native-hydra-consent) distinguish current approval checks, requests crossing token persistence, and approval between bulk cleanup calls. These do not qualify every provider-internal interleaving. No production token hook, credential inventory or recovery release wiring follows from this decision.

## Implementation notes

[Development Compose](../../compose.dev.yaml) configures native Kratos-to-Hydra login, private administration and an explicit CLI client setup step before API startup. The JSON consent API is not configured as a browser page. The [setup guide](../development/getting-started/local-setup.md#configure-the-cli-client) explains UI placeholders and native lifetime configuration. This does not wire production recovery completion.

`_read_supported_request()` rejects unsupported access with 403 before browser verification or local-state work, including with an invalid supplied cookie. HTTP credential selection and CSRF retain precedence. Inspection and denial share `_check_read_only_request()`. Approval uses `_prepare_approval()` to capture state, verify the browser, reread state and return a required credential binding under ADR-0072. Denial submits its provider decision only after read-only checks. No optional binding, new workflow framework or automatic approval retry is introduced.

## Links

- [ADR-0053: Kratos and Hydra for human CLI authentication](ADR-0053-use-kratos-and-hydra-for-human-cli-authentication.md)
- [ADR-0070: Bulk recovery revocation](ADR-0070-use-bulk-hydra-revocation-for-identity-recovery.md)
- [Consent service](../../apps/backend/src/inframeld_backend/access/application/services/human_oauth_consent_service.py)
- [Native login and consent tests](../../apps/backend/tests/integration/access/test_native_hydra_consent.py)
- [Token-hook qualification](../../apps/backend/tests/integration/access/test_hydra_token_hook_cleanup.py)
- [Pinned native integration](https://github.com/ory/kratos/blob/v26.2.0/hydra/hydra.go)
- [Current provider versions and security review](../../.agents/skills/inframeld-architecture/references/runtime-deployment-and-storage.md)
- [Ory login and consent flow](https://www.ory.com/docs/oauth2-oidc/custom-login-consent/flow)

[ADR-0072](ADR-0072-version-human-cli-credentials-across-account-recovery.md) adds durable versions without changing native login or bulk cleanup. Late grants can remain active at Hydra while failing Inframeld authentication after block release. Production completion remains unwired until trusted native evidence and durable execution are qualified.
