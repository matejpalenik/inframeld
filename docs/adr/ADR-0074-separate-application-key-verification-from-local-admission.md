# ADR-0074: Separate application-key verification from local admission

**Status:** Accepted

**Date:** 2026-10-25

## Context and Problem Statement

SupportBot supplies an Inframeld application key to query Production. The backend must verify the complete credential, check whether its existing application account is currently eligible, and authorize the exact operation. A public key ID or a successful earlier login cannot answer all three questions.

The accepted application-key contract already selects the format, stored verifier, lifetime, audience checks and lifecycle rules. Application-key authentication remains unfinished. The implemented browser service provides an example of separate credential verification and local admission, but it does not implement the application-key path.

## Considered Options

- One application authenticator performs key lookup/verification and local admission. This needs fewer collaborators, but couples credential failure handling with account-policy concerns and their tests.
- A focused key-verification capability supplies safe identity/evidence to a coordinating application authentication service. This makes the trust responsibilities explicit and independently testable, at the cost of another contract whose freshness and failures must be specified. This is selected.

For the verifier result, two shapes were considered:

- Return only the verified key ID and its associated application principal ID. The authentication service loads the current account separately and applies admission rules. This keeps verification focused, with a separate account read. This is selected.
- Return the key identity together with account facts observed during verification. This may save a database read, but couples the verification result to the account representation. Admission would still belong to the authentication service.

For expected credential rejection, the existing browser-verifier pattern is selected: return no verified result. A dedicated rejection exception was also considered. It can preserve the same public outcomes, but adds a different exception path from the established verifier contract. Required dependency failure remains an exception in either approach.

For later current-key checks, existing Access authorizers are selected. They can obtain current credential facts alongside their account/permission facts, keeping one authorization capability for consuming domains. A separate credential guard called by every application service was considered, but would add another mandatory call that each consumer must coordinate correctly.

## Decision Outcome

Access owns both components. The focused verification capability verifies the complete application credential against its stored verifier and required credential bindings/lifecycle checks. It returns a minimal internal record containing only `ApplicationKeyId` and the associated `PrincipalId`, obtained from the verified stored key/account binding. It contains no credential secret, verifier digest, account state or grants. Caller-supplied IDs alone cannot establish this result.

An instantiated application authentication service invokes that capability through an injected application-owned contract. It uses the returned principal ID to load the current application account through a focused reader, applies current local admission checks and then constructs the required `AccessContextDTO`. The context contains the actor ID and `ApplicationKeyAuthenticationDTO` carrying the verified key ID. The intermediate two-ID result is distinct from this final authentication context. Credential secrets, mutable account state and permissions do not enter that context. Infrastructure implements credential I/O behind the application contract, following existing component conventions.

A valid credential returns the minimal result. An invalid, expired or revoked credential returns `None`. The authentication service translates that absence to `AuthenticationRequiredError` before account loading. Recognized verification-dependency availability failures raise `DependencyUnavailableError`. Unexpected failures and cancellation propagate rather than becoming credential rejection. Verification exceptions do not authorize credential fallback or cached success.

The HTTP boundary retains the existing generic 401 and 503 mappings. After successful verification, a current local admission denial remains a separate 403 outcome. The verifier returns application values or raises application errors, without constructing HTTP responses. These are accepted contracts for the future application-key path.

Existing Access authorizers own fresh stored application-key checks for incoming protected operations and replays. They use the `ApplicationKeyId` in `AccessContextDTO` to obtain current key facts and check its actor binding, expiry and revocation alongside current account, action and protected-input authority. These checks run before protected work or replay. Initial secret verification remains with the verifier. Authorizers do not require retaining or forwarding the secret.

For writes, the checks participate in the operation's transaction and applicable coordination rules. Application services continue calling their existing Access authorization capability rather than adding a separate mandatory credential-guard call. Infrastructure readers obtain facts, and Access-owned application evaluation/domain policies interpret them under the existing query/policy boundary. Authentication evidence is not a permission certificate. Reject competing credential mechanisms before verification, and do not fall back to Hydra, a browser session or another credential after failure.

These components run inside the existing modular backend. This decision adds no network service, account provisioning, implicit key issuance or generic authentication framework. The accepted key format, SHA-256 verifier, lifetime, two-usable-key limit, show-once delivery and current-account authority remain governed by the existing key contract.

## Consequences

Credential verification, account admission and operation authorization have explicit owners. Tests can exercise invalid credentials and ineligible accounts independently, while the authentication service coordinates the complete path.

The minimal result adds a separate account read and keeps account loading/eligibility in the authentication service. Its logical values are defined in the data model. Expected credential rejection and verification-dependency failure now have a settled internal contract. The existing authorizers' ownership of fresh key-state checks is settled. Exact verification inputs, expiry/revocation checkpoint and concurrency mechanics, and the credential lifecycle of already-admitted background work still need specification. This decision does not settle those temporal details or reinterpret the existing human OAuth generation flag as proof of application-key validity. Concrete record names, method signatures, physical schema and a locking algorithm are not selected here.

Application-key authentication and production qualification remain unfinished. The existing human paths and recovery boundaries are unchanged. No ADR is superseded by this component-boundary decision.

## Links

- [Current application-key architecture and remaining contracts](../../.agents/skills/inframeld-access-models/references/application-keys.md#application-key-authentication-boundary).
- [Accepted key verification and lifetime](../../.agents/skills/inframeld-access-models/references/application-key-contracts.md#application-key-contract).
- [Minimal verified-key result](../../.agents/skills/inframeld-access-models/references/credential-and-recovery-records.md#application-key-verification-result), [authentication evidence records](../../.agents/skills/inframeld-access-models/references/credential-and-recovery-records.md#authentication-evidence-records) and [ADR-0073](ADR-0073-carry-explicit-authentication-evidence-in-access-contexts.md).
- [Current account authority](ADR-0017-let-valid-application-keys-use-current-account-permissions.md) and [opaque application credentials](ADR-0018-use-opaque-expiring-and-revocable-application-credentials.md).
- [Current-key authorization ownership](../../.agents/skills/inframeld-access-models/references/application-keys.md#application-key-current-authorization).
- [Verification outcomes](../../.agents/skills/inframeld-access-models/references/application-key-contracts.md#verification-results-and-unresolved-currentness) and [accepted public authentication errors](../development/error-handling.md#authentication-contract).
- [Inspected browser verifier contract](../../apps/backend/src/inframeld_backend/access/application/protocols/browser_session_verifier.py). Its rejection/availability pattern is reused, while application-key implementation remains unfinished.
- [Component conventions](../../.agents/skills/inframeld-python-standards/references/component-roles-and-imports.md#component-conventions) and [inspected browser authentication service](../../apps/backend/src/inframeld_backend/access/application/services/human_session_authentication_service.py). The browser implementation is an ownership example, not application-key implementation evidence.

## Later resolution

[ADR-0100](ADR-0100-order-key-revocation-at-protected-boundaries.md) resolves key-boundary ordering, and [ADR-0101](ADR-0101-authorize-admitted-jobs-by-current-principal.md) resolves admitted-job authority, both approved on 2026-10-29. The earlier verification/authentication component choice remains accepted.
