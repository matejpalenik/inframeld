# ADR-0130: Observe private Kratos password verifiers for invitations

**Status:** Accepted and implemented for the invitation-specific verifier. The three configured real-Kratos verifier cases are qualified.

**Date:** 2026-11-07

## Context and Problem Statement

Bob signs in through OIDC and activates Alice's invitation. Fresh activation requires password setup, but Bob's current login need not use a password. A password authentication-method record describes that login, not the identity's complete credential state.

The first real provider check found that Kratos v26.2.0 creates a password credential slot for an OIDC identity that has never set a password. Ordinary private identity output removes credential configuration from both empty slots and real password credentials. Slot presence, identifiers, version and timestamps cannot establish password completion. The failed case stopped before calling the invitation verifier. It did not observe a verifier false positive.

The reviewed invitation plan initially prohibited requesting credential configuration or observing password hashes. That restriction cannot supply the required distinction through this pinned API. Ordinary identity verification and application authorization remain separate.

## Considered Options

- Keep that restriction and block fresh activation until an authoritative nonsecret provider fact is available. This avoids the additional sensitive observation but cannot complete the accepted invitation behavior now.
- Permit one confidential observation through the existing private Kratos SDK, reducing its result immediately to a boolean. This adds sensitive data to transient backend memory and requires containment through decoding, exceptions and diagnostics.

Neither current-session AMR nor metadata heuristics replace password setup. A new callback ledger, provider endpoint or mandatory password reauthentication was not selected.

## Decision Outcome

The developer approved the second option and its documentation on 2026-11-07. Only the invitation-specific verifier may call the configured private `IdentityApi.get_identity` with `include_credential=['password']`, using the exact UUID established by the current configured Kratos session. The additional call shares the original monotonic provider deadline and stays outside SQL transactions.

One synchronous confidential boundary owns the SDK call, parsing, exact active-identity checks and reduction to current stored nonempty password-verifier presence. No `Identity`, credential configuration or hash crosses that boundary. A missing or empty verifier is false. A nonempty stored string is true. Malformed or unavailable evidence cannot become permission. Migration-hook-only state without a stored verifier is not true. This fact establishes neither password usability, a fresh password login nor permanent onboarding history.

Reject enabled SDK or wire debugging before I/O without changing global settings. Known SDK and validation failures produce only safe outcomes or fixed safe errors. A narrow `Exception` catch around this confidential operation preserves unexpected failure as a fixed safe 500 raised after the catch, with no raw cause or context. The existing bounded structural diagnostic records only original exception types and frame locations. `BaseException` and cancellation propagate. Do not persist, return, audit, log or capture credential configuration or hashes. Do not claim Python memory zeroization.

Preview performs no password observation. Completed replay still requires the same currently verified eligible recipient, but does not require a fresh password observation or its availability. A bounded observation may have been prepared before SQL. Only fresh activation requires the true fact after original-result lookup. All other authority, identity, recovery, transaction and replay safeguards remain unchanged.

## Consequences

This decision narrowly replaces the invitation plan's earlier no-configuration/no-hash-observation guarantee. It does not change the ordinary human identity verifier's no-credential-read contract or the nonsecret application-context, result, persistence, audit and diagnostic boundaries. No public credential endpoint or local password verification is introduced.

Focused component checks qualified placeholder rejection, safe SDK/validation/unexpected-error paths, debug refusal, unchanged budgets and confidentiality for direct callers and ASGI rethrows. The later real-Kratos qualification passed all three cases: password registration/login, never-password OIDC and an already password-onboarded identity retaining its valid OIDC-only session. The first failed provider run remains failed. This evidence qualifies the verifier boundary consumed by implemented invitation activation, registered HTTP operations and generated-client interfaces. It does not establish account-UI onboarding or human acceptance.

## Links

- [Invitation authority and atomic activation](ADR-0062-activate-invitations-under-current-issuer-authority.md).
- [Invitation password observation](../../.agents/skills/inframeld-access-models/references/admission-and-invitations.md#invitation-password-observation).
- [Password-completion contract](../../.agents/skills/inframeld-access-models/references/invitation-contracts.md#password-completion-observation).
- [Safe diagnostics](../../.agents/skills/inframeld-application-contracts/references/safe-diagnostics.md).
- Pinned Kratos [placeholder creation](https://github.com/ory/kratos/blob/v26.2.0/identity/extension_credentials.go#L32-L48), [configuration redaction](https://github.com/ory/kratos/blob/v26.2.0/identity/identity.go#L439-L447) and [password persistence](https://github.com/ory/kratos/blob/v26.2.0/selfservice/strategy/password/registration.go#L143-L147).
