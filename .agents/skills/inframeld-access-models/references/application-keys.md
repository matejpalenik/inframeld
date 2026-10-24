# Application accounts and keys

Alice connects SupportBot to Production. Giving the bot her browser cookie or CLI token would make it act as Alice. Instead, the bot has a separate project-bound application account and its own incoming Inframeld credential.

## Identity, permissions and issuance

An application key identifies its account. The account's current permissions determine what a valid key may do. Issuance is not a permanent permission ceiling copied onto that key. Removing a grant or suspending/deleting the account takes effect under current checks even while the key bytes stay unchanged.

Human and application principals share the local membership and grant model, but applications receive only eligible use permissions. They cannot acquire human-only delegation, incoming-credential administration, group management or budget-policy administration. Application HTTP/MCP clients use Inframeld keys, with no implicit Hydra client-credentials grant. Saved provider secrets serve a different outbound purpose.

## Follow the connection journey

1. Review the application's existing account, document-group scope and exact action grants. An integration needing Deployment Query does not silently gain Pipeline Query or release authority.
2. An authorized human passes both required account/key-management and delegation checks. Account creation, permission assignment and key issuance are distinct operations. Setup does not issue a key automatically.
3. Issue the secret through the ordinary show-once delivery contract. Preserve the two-usable-key limit, lifecycle restrictions and exact audience/adapter checks.
4. The client supplies the accepted application credential. The public `ifm_app_` prefix selects recognition but is not proof of identity or authority. Full syntax, stored-verifier, expiry, revocation and account checks remain mandatory. Leave Ory token formats unchanged and never try another credential kind after failure.
5. The operation checks current project/action/document authority. Rotation changes the credential without changing the account's grants or document-group membership.

The CLI can accept an existing application key through hidden paste or its reviewed automation input. This is separate from issuance and human login. The application-connection wizard may offer a separately approved paid test, but verification must not hide a paid query or widen scope.

## Lost responses and partial effects

Show-once delivery means the original successful response is the only opportunity to obtain the secret. Replay cannot recover it. A timeout/nonzero CLI exit is not proof that issuance failed or authority to create another key.

Keep retry fingerprints keyed and secret-safe, with outcome metadata explaining whether issuance completed or needs explicit recovery. Do not store plaintext in idempotency, audit, traces or logs.

Overlap limits, expiry, revocation and account deletion solve different lifecycle problems. Removal permanently stops the account, revokes keys and removes its relationships without erasing project-owned documents or reassigning historical actions to a human. Retained attribution follows retention/erasure rules and must never reactivate the identity.

## Status and sources

The prefix, credential dispatch, complete key format/lifetimes and account-authority rules are accepted design. Application-key verification and remaining lifecycle/runtime qualification are unfinished. Authorization fixtures simulating key IDs do not establish provisioning or an authenticator.

MCP retains the accepted preconfigured, header-capable two-tool profile without implied OAuth discovery or verified user delegation.

- [Application authority](../../../../docs/development/access-control.md#applications), [key recognition](../../../../docs/development/access-control.md#application-key-prefix), [full verification/lifetimes](../../../../docs/development/access-control.md#application-key-contract), [key input](../../../../docs/development/access-control.md#cli-application-key-input) and [credential dispatch](../../../../docs/development/access-control.md#credential-dispatch).
- [Secret retry contract](../../../../docs/development/jobs-and-idempotency.md), [Access key lifecycle](../../../../docs/development/access-contracts.md#key-lifecycle), [identity records](../../../../docs/development/data-model.md#access) and [MCP authentication](../../../../docs/development/mcp.md#authentication).
- [ADR-0017](../../../../docs/adr/ADR-0017-let-valid-application-keys-use-current-account-permissions.md) explains current permissions. [ADR-0018](../../../../docs/adr/ADR-0018-use-opaque-expiring-and-revocable-application-credentials.md) explains opaque, expiring, revocable credentials.
