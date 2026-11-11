# Application-key format and transport contracts

Alice issues SupportBot a key and loses the response. The first successful delivery can contain the secret. A safe replay contains metadata only. The key’s public identifier is not proof of validity or current authority.

> **Status:** Safe metadata reads, application-key authentication and strict issuance are implemented. Individual revocation is implemented through the registered route and safe original-result storage. Native OpenAPI and the three selected generated clients cover that operation and its actual models. Deployment and human qualification remain separate. [Permanent account retirement](application-keys.md#retiring-supportbot-does-not-delete-its-work) has its own registered operation and retained result. Metadata reads do not issue credentials.

<a id="application-key-contract"></a>

<a id="verify-a-complete-key-and-bound-its-lifetime"></a>

## Verify a complete key and bound its lifetime

The accepted key format is `ifm_app_<key-UUID>_<secret>`. Generate the public key ID as UUIDv4 and the secret from **32 cryptographically random bytes**, encoded as unpadded base64url, producing 43 secret characters. The public UUID identifies the verifier record to load. It is not the application principal and proves nothing about the caller. This generation rule does not change the valid UUID values accepted by existing application-owned identifier types.

Store **SHA-256 of the complete canonical key** as the verifier bytes, together with safe identity/binding/lifecycle metadata. Compare verifier bytes in constant time after validating the supported key syntax. Do not store or return plaintext for later retrieval, expose the secret in validation messages, or treat lookup by public UUID as authentication. Full verification includes the key's installation, audience/adapter, expiry and revocation, plus current application principal, account, project binding and lifecycle state. Authorization separately checks current grants and protected inputs.

The default lifetime is **90 days**, with a **365-day maximum**. Both are operator-configurable. Authorized issuance may select a shorter lifetime, and there is no automatic renewal. An operator's configured default must fit its configured maximum. These incoming-key durations do not replace the separate Hydra/Kratos lifetime settings. The safe record fields belong to [the logical key contract](credential-and-recovery-records.md#application-key-record-contract).

The accepted issuance mapping binds each selected adapter to its explicit server-owned profile. HTTP-only selects the configured HTTP audience, MCP-only selects the canonical MCP resource, and selecting both retains both bindings. The audiences may be equal or different. One key still has one public ID, secret, verifier and place in the two-usable-key limit. Callers supply no audience, and verification compares only the binding for its trusted adapter without aliases or normalization. Issuance implements these fixed bindings and their storage extension, covered by the selected generated clients.

Keep the two-usable-key limit across audiences and explicit issue/update-consumers/revoke replacement sequence. Issuance still performs every [current delegation and group-management check](application-keys.md#applications), coordinated with competing scope changes. Display the secret only on the original successful delivery. A lost response yields the safe [show-once retry outcome](application-keys.md#secrets), never plaintext replay. The issuance service implements this format and configured lifetime selection. Its current generated-client and whole-feature qualification must be established separately.

The public `ifm_app_` prefix contributes no secret entropy and encodes neither installation nor application identity, Project or permissions. `ifm_app_...` is a placeholder, not a usable credential. A prefix alone cannot authenticate anyone, and absence of the prefix does not prove a human OAuth credential. Never send a failed application key to Hydra. Selected Kratos/Hydra human token formats remain unchanged. No enterprise Ory token-format customization is required.

## Implemented issuance boundary

The implementation registers [the issuance route](../../../../apps/backend/src/inframeld_backend/access/http/routes/application_key_issuance_routes.py) over [ApplicationKeyIssuanceService](../../../../apps/backend/src/inframeld_backend/access/application/services/application_key_issuance_service.py). Current eligible-human Project membership, exact Issue authority, every held-permission delegation and every group-management requirement precede original-result disclosure. Fresh issuance then validates the reviewed revision, selected profiles, lifetime and two-parent-key cap under coordinated current reads.

Key/verifier/bindings, one Project revision advance, required audit and immutable safe original result commit together. Only the original first delivery carries plaintext. A completed exact replay returns HTTP `201` with `secretAvailable: false` and the credential field absent, before fresh profile, lifetime and slot checks. It preserves historical metadata even after later expiry/revocation or configuration changes. It neither rebinds nor renews anything. Known rollback leaves no effects; uncertain commit/response remains unconfirmed without automatic retry or replacement.

[The user task](../../../../apps/docs/src/app/guides/application-accounts/page.mdx#issue-a-key) uses the existing genuine browser-cookie acquisition path. Issuance does not revoke or replace an old key. It does not claim a saved human CLI login, metadata CLI, retirement or mounted MCP journey. [Human qualification #358](https://github.com/matejpalenik/inframeld/issues/358) remains unready and Not run. Required SDK/runtime qualification is engineering acceptance, separate from that deferred human work.

## Implemented revocation boundary

The implementation registers [the revocation route](../../../../apps/backend/src/inframeld_backend/access/http/routes/application_key_revocation_routes.py) over [ApplicationKeyRevocationService](../../../../apps/backend/src/inframeld_backend/access/application/services/application_key_revocation_service.py). Its strict `ApplicationKeyRevocationRequest` contains only `expectedAccessRevision`, bounded from zero through the safe-integer maximum. Bind the original `Idempotency-Key` to the concrete POST route, Project, application principal and key. This is a separate human operation, not an application-key-authenticated request or an issuance fallback.

Current eligible-human Project membership and exact Revoke keys use authority precede original-result disclosure. Issue, Delete, issuance delegation and group management are independent. The coordinated write sets the key's revocation timestamp, advances the Project Access revision once and saves its audit and safe original result together. It may revoke the last usable key. Revoking a dual-adapter parent disables both bindings without removing the account or its grants.

HTTP `200` returns `operationId`, captured `accessRevision`, `idempotencyExpiresAt` and safe nested metadata, never a secret or verifier. A fresh request for an already revoked key checks its current reviewed revision, retains the existing timestamp and saves a no-op original without another revision advance or revocation audit. An exact completed replay checks current authority and returns its historical metadata before fresh revision checks, without repeating effects or renewing retention. The [user task](../../../../apps/docs/src/app/guides/application-accounts/page.mdx#revoke-one-application-key) owns explicit same-request recovery. No generic operation-lookup authority is added.

Unknown commit or response state never authorizes automatic redispatch, another request key or replacement issuance. New incoming requests through a revoked key fail current verification and protected checks. Already committed effects cannot be undone by revocation, while [admitted work](decision-admitted-work-authority.md#approved-resolution) retains its separate current-principal authority contract. This route does not implement account retirement, physical erasure or a mounted MCP workflow.

## Key-management routes

| Method and route | Operation ID | Named input / result | Authority and success |
| --- | --- | --- | --- |
| `POST /v1/projects/{project_id}/application-accounts/{application_principal_id}/keys` | `issueApplicationKey` | `ApplicationKeyIssueRequest` / `ApplicationKeyIssueResponse` | Exact `issue-application-keys` plus every current delegation/group check. 201. |
| `GET` at the same keys route | `listApplicationKeys` | Pagination query / `PageResponse[ApplicationKeyMetadataResponse]` | Exact Issue or Revoke keys. 200. Key UUID order, safe metadata only. |
| `GET` at that route plus `/{key_id}` | `getApplicationKey` | No body / `ApplicationKeyMetadataResponse` | Exact Issue or Revoke keys. 200. No secret retrieval. |
| `POST` at that route plus `/{key_id}/revoke` | `revokeApplicationKey` | `ApplicationKeyRevocationRequest` / `ApplicationKeyRevocationResponse` | Exact `revoke-application-keys`. 200. Immediate revocation independent of issuance delegation. |

<a id="application-key-metadata-reads"></a>

### Implemented safe metadata reads

`listApplicationKeys` and `getApplicationKey` use the GET rows above. [ApplicationAccountReadService](../../../../apps/backend/src/inframeld_backend/access/application/services/application_account_read_service.py) requires current eligible human authority and Project membership before returning metadata. Any administration action establishes account visibility, while the key read separately requires exact Issue or Revoke use. Delete alone returns 403 for key metadata on an otherwise visible account. Neither read requires the additional issuance delegation or group-management checks.

The [PostgreSQL reader](../../../../apps/backend/src/inframeld_backend/access/infrastructure/readers/postgres_application_account_facts_reader.py) observes current caller facts, exact account binding and safe metadata in one statement. Its explicit key projection never fetches the verifier, audience or original secret. Lists include retained expired/revoked records, ordered by key UUID, with default 25 and limit 1–100. An endpoint-owned opaque cursor binds installation, Organization, Project, account principal and UUID position. Each continuation is a fresh authorized observation, not a snapshot or authority token. Empty continuations retain the authorization header. Invalid or incompatible cursors return `invalid_input` 422.

The native `ApplicationKeyMetadataResponse` has exactly the documented safe fields. There is no secret retrieval endpoint. Account create/get/exact-Name inspection follows [the owning workflow](application-keys.md#implemented-application-account-creation). Issuance, full verification and individual revocation are implemented. [Account retirement](application-keys.md#retiring-supportbot-does-not-delete-its-work) revokes every key through its separate authorized operation.

## Typed response alternatives

**Illustrative notation, not importable declarations.** Issuance uses native `ApplicationKeyIssueRequest`, `ApplicationKeyIssueResponse`, `ApplicationKeyFirstDeliveryResponse` and `ApplicationKeyIssuanceReplayResponse`. Revocation has native `ApplicationKeyRevocationRequest` and `ApplicationKeyRevocationResponse` declarations in its HTTP owner. The common teaching names below explain their wire alternatives. UUID and datetime denote JSON string forms, and unknown fields are rejected. Read the exported native schema and actual generated models before using client symbols.

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

Fresh issuance requires every selected adapter profile. A missing selected profile returns safe 503 before secret creation, with no partial credential. An unselected missing profile is irrelevant. `expiresInSeconds` accepts positive whole seconds, rejects explicit null, booleans and fractions, and must fit the configured maximum for fresh issuance. Preserve the exact original body, adapter order, omitted lifetime and request key during recovery. Current-authorized completed replay returns its original safe metadata and expiry before fresh profile, lifetime and slot checks. It neither applies today's configuration nor binds another resource.

## Failures and safe recovery

Issuance requires exact human Issue keys authority, delegation for every current account permission and management of every current account group, rechecked with current account/Project state at commit. The two-usable-key limit is coordinated across audiences. A race cannot silently revoke an old key to free a slot.

Metadata list/get needs exact Issue or Revoke keys, without the extra issuance delegation check. Delete account alone is insufficient. It returns no secret or verifier. Listing uses existing bounded pagination and key-UUID order. Revocation needs its independent exact Revoke keys authority and may revoke the last usable key immediately.

First delivery contains the newly created secret. The same original issuance replay omits it and reports `secretAvailable: false`. Never save plaintext in idempotency, audit, trace or logs, and never generate another key because a response was lost. The retained metadata describes the original created credential. A fresh authorized read determines its current expiry/revocation state. A human may explicitly revoke the unusable lost key and admit a separate new issuance.

A known rollback leaves no partial issuance. An uncertain COMMIT acknowledgment does not establish rollback and cannot authorize automatic retry or replacement. Recover the original request under current authority without recovering plaintext. A validated first 201 followed by local secret-storage failure instead confirms issuance with failed local delivery. Neither outcome authorizes automatic reissuance.

<a id="verification-results-and-unresolved-currentness"></a>

## Verification results and currentness

[ADR-0074](../../../../docs/adr/ADR-0074-separate-application-key-verification-from-local-admission.md) selects a focused verifier returning only verified key identity and associated principal identity. Do not invent a concrete result schema or new account snapshot here. The authentication service separately loads the account, checks local eligibility and builds complete non-secret evidence.

Credential rejection returns `None` before account loading. Recognized required-verification dependency failures raise `DependencyUnavailableError`. Unexpected errors and cancellation propagate. Preserve safe 401 for invalid credentials, 503 for unconfirmed verification dependencies and separate 403 for verified but locally ineligible accounts.

Existing authorizers own later fresh key-state checks through key-ID evidence. The consuming service uses its ordinary Access authorization capability. No extra mandatory credential-guard call is introduced. The accepted [PD-ACCESS-01](decision-key-currentness.md#approved-resolution) selects complete credential plus trusted installation/audience/adapter input, current database expiry checks after coordination waits, and protected-boundary ordering. [PD-ACCESS-02](decision-admitted-work-authority.md#approved-resolution) selects current-principal authority for admitted jobs. The verifier and current-key facts are implemented under [the owning authentication boundary](application-keys.md#application-key-authentication-boundary). This does not supply an admitted-job worker or mounted MCP server.

## Sources and limits

[Application keys](application-keys.md) owns the account and rotation workflow. [Credential records](credential-and-recovery-records.md#application-key-record-contract) explain safe retained binding/lifecycle information. [ADR-0018](../../../../docs/adr/ADR-0018-use-opaque-expiring-and-revocable-application-credentials.md) records opaque expiration/revocation. Only generated key IDs require UUIDv4. Current account grants remain independent from the key record.
