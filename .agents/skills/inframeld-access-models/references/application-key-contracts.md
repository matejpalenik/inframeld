# Application-key format and transport contracts

Alice issues SupportBot a key and loses the response. The first successful delivery can contain the secret. A safe replay contains metadata only. The key’s public identifier is not proof of validity or current authority.

> **Status:** Accepted key format/lifetimes and documented transport drafts. No production key authenticator or key-management routes are established here.

<a id="application-key-contract"></a>

<a id="verify-a-complete-key-and-bound-its-lifetime"></a>

## Verify a complete key and bound its lifetime

The accepted key format is `ifm_app_<key-UUID>_<secret>`. Generate the public key ID as UUIDv4 and the secret from **32 cryptographically random bytes**, encoded as unpadded base64url, producing 43 secret characters. The public UUID identifies the verifier record to load. It is not the application principal and proves nothing about the caller. This generation rule does not change the valid UUID values accepted by existing application-owned identifier types.

Store **SHA-256 of the complete canonical key** as the verifier bytes, together with safe identity/binding/lifecycle metadata. Compare verifier bytes in constant time after validating the supported key syntax. Do not store or return plaintext for later retrieval, expose the secret in validation messages, or treat lookup by public UUID as authentication. Full verification includes the key's installation, audience/adapter, expiry and revocation, plus current application principal, account, project binding and lifecycle state. Authorization separately checks current grants and protected inputs.

The default lifetime is **90 days**, with a **365-day maximum**. Both are operator-configurable. Authorized issuance may select a shorter lifetime, and there is no automatic renewal. An operator's configured default must fit its configured maximum. These incoming-key durations do not replace the separate Hydra/Kratos lifetime settings. The safe record fields belong to [the logical key contract](credential-and-recovery-records.md#application-key-record-contract).

Keep the two-usable-key limit across audiences and explicit issue/update-consumers/revoke replacement sequence. Issuance still performs every [current delegation and group-management check](application-keys.md#applications), coordinated with competing scope changes. Display the secret only on the original successful delivery. A lost response yields the safe [show-once retry outcome](application-keys.md#secrets), never plaintext replay. Algorithm, format and lifetime selection are accepted design. Still needs their implementation and behavioral qualification.

The public `ifm_app_` prefix contributes no secret entropy and encodes neither installation nor application identity, Project or permissions. `ifm_app_...` is a placeholder, not a usable credential. A prefix alone cannot authenticate anyone, and absence of the prefix does not prove a human OAuth credential. Never send a failed application key to Hydra. Selected Kratos/Hydra human token formats remain unchanged. No enterprise Ory token-format customization is required.

## Draft key-management routes

| Method and route | Operation ID | Named input / result | Authority and success |
| --- | --- | --- | --- |
| `POST /v1/projects/{project_id}/application-accounts/{application_principal_id}/keys` | `issueApplicationKey` | `ApplicationKeyIssueRequest` / `ApplicationKeyIssueResponse` | Exact `issue-application-keys` plus every current delegation/group check. 201. |
| `GET` at the same keys route | `listApplicationKeys` | Pagination query / `PageResponse[ApplicationKeyMetadataResponse]` | Exact Issue or Revoke keys. 200. Key UUID order, safe metadata only. |
| `GET` at that route plus `/{key_id}` | `getApplicationKey` | No body / `ApplicationKeyMetadataResponse` | Exact Issue or Revoke keys. 200. No secret retrieval. |
| `POST` at that route plus `/{key_id}/revoke` | `revokeApplicationKey` | `ApplicationKeyRevocationRequest` / `ApplicationKeyRevocationResponse` | Exact `revoke-application-keys`. 200. Immediate revocation independent of issuance delegation. |

## Typed response alternatives

**Design notation, not production implementation.** UUID and datetime denote their JSON string forms. Unknown fields are rejected. The common teaching names distinguish delivery cases without changing the documented `ApplicationKeyIssueResponse` symbol.

```python
from datetime import datetime
from typing import Literal, Never, NotRequired, TypedDict
from uuid import UUID

class ApplicationKeyIssueRequest(TypedDict):
    allowedAdapters: list[Literal["http", "mcp"]]  # Nonempty and unique.
    expiresInSeconds: NotRequired[int]  # Strict positive, within configured max.
    expectedAccessRevision: int  # Strict nonnegative revision.

class ApplicationKeyRevocationRequest(TypedDict):
    expectedAccessRevision: int

class ApplicationKeyMetadataResponse(TypedDict):
    keyId: UUID
    applicationPrincipalId: UUID
    projectId: UUID
    prefix: Literal["ifm_app_"]  # Only this public prefix, never secret bytes.
    allowedAdapters: list[Literal["http", "mcp"]]
    createdAt: datetime
    expiresAt: datetime
    revokedAt: datetime | None

class ApplicationKeyIssueResult(TypedDict):
    operationId: str
    accessRevision: int
    idempotencyExpiresAt: datetime
    metadata: ApplicationKeyMetadataResponse

class ApplicationKeyFirstDelivery(ApplicationKeyIssueResult):
    secretAvailable: Literal[True]
    key: str

class ApplicationKeyIssuanceReplay(ApplicationKeyIssueResult):
    secretAvailable: Literal[False]
    key: NotRequired[Never]

type ApplicationKeyIssueResponse = ApplicationKeyFirstDelivery | ApplicationKeyIssuanceReplay

class ApplicationKeyRevocationResponse(TypedDict):
    operationId: str
    accessRevision: int
    idempotencyExpiresAt: datetime
    metadata: ApplicationKeyMetadataResponse
```

Bind the key to both account and Project in the path. Installation and API-audience bindings come from authoritative server configuration, not a caller-supplied permission set. `allowedAdapters` is a required nonempty unique subset. Omitted lifetime uses the configured default. Revocation accepts only the expected revision. [Access mutation bounds](grant-contracts.md#shared-wire-field-bounds-and-owner-specific-handoffs) still apply.

## Failures and safe recovery

Issuance requires exact human Issue keys authority, delegation for every current account permission and management of every current account group, rechecked with current account/Project state at commit. The two-usable-key limit is coordinated across audiences. A race cannot silently revoke an old key to free a slot.

Metadata list/get needs exact Issue or Revoke keys, without the extra issuance delegation check. Delete account alone is insufficient. It returns no secret or verifier. Listing uses existing bounded pagination and key-UUID order. Revocation needs its independent exact Revoke keys authority and may revoke the last usable key immediately.

First delivery contains the newly created secret. The same original issuance replay omits it and reports `secretAvailable: false`. Never save plaintext in idempotency, audit, trace or logs, and never generate another key because a response was lost. The retained metadata describes the original created credential. A fresh authorized read determines its current expiry/revocation state. A human may explicitly revoke the unusable lost key and admit a separate new issuance.

## Verification results and unresolved currentness

[ADR-0074](../../../../docs/adr/ADR-0074-separate-application-key-verification-from-local-admission.md) selects a focused verifier returning only verified key identity and associated principal identity. Do not invent a concrete result schema or new account snapshot here. The authentication service separately loads the account, checks local eligibility and builds complete non-secret evidence.

Credential rejection returns `None` before account loading. Recognized required-verification dependency failures raise `DependencyUnavailableError`. Unexpected errors and cancellation propagate. Preserve safe 401 for invalid credentials, 503 for unconfirmed verification dependencies and separate 403 for verified but locally ineligible accounts.

Existing authorizers own later fresh key-state checks through key-ID evidence. The consuming service uses its ordinary Access authorization capability. No extra mandatory credential-guard call is introduced. The accepted [PD-ACCESS-01](decision-key-currentness.md#approved-resolution) selects complete credential plus trusted installation/audience/adapter input, current database expiry checks after coordination waits, and protected-boundary ordering. [PD-ACCESS-02](decision-admitted-work-authority.md#approved-resolution) selects current-principal authority for admitted jobs. These logical contracts do not claim an implemented verifier or worker.

## Sources and limits

[Application keys](application-keys.md) owns the account and rotation workflow. [Credential records](credential-and-recovery-records.md#application-key-record-contract) explain safe retained binding/lifecycle information. [ADR-0018](../../../../docs/adr/ADR-0018-use-opaque-expiring-and-revocable-application-credentials.md) records opaque expiration/revocation. Only generated key IDs require UUIDv4. Current account grants remain independent from the key record.
