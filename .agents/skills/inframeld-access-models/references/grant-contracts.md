# Exact-target grant transport contracts

Alice changes Bob’s permission on one resource. The request identifies that resource through its concrete route, with reviewed state and original operation identity. These contracts do not introduce a generic grant endpoint.

<a id="mutation-profile"></a>

<a id="bounded-access-mutation-profile"></a>

## Bounded Access mutation profile

New Access-management JSON bodies are limited to **32 KiB (32,768 bytes)**. New bulk assignment requests carry at most **100 explicit assignments**. Reject unknown fields in new request schemas. These limits do not apply to document uploads or complete domain configuration payloads. Preserve existing published schema names, field behavior and restrictions rather than silently tightening them through a shared replacement model.

Use camelCase wire fields, UUID strings for known resource identities, an opaque string `operationId`, UTC timestamps and strictly nonnegative integer revisions. Access writes carry `expectedAccessRevision`. Other owners retain their domain-specific revision inputs. Every mutation carries exactly one `Idempotency-Key`, at most 128 characters. The original operation is found before treating today's revision as a new write, with current authentication/authorization still required to recover it. [Jobs and idempotency](../../inframeld-application-contracts/references/idempotency-and-replay.md#requests) own request identity and recovery.

A local change saves its domain effects, revision, audit and original outcome together. Use 201 for creation, 200 for completed metadata changes and 202 when durable cleanup remains. Return the original operation identity, appropriate resource identity, committed revision and safe outcome through the owning operation's typed result. A 202 response means accepted work, not completed erasure. This profile does not introduce a generic operation envelope or command framework. The [concrete HTTP draft](#http-operation-matrix) supplies the new request/response symbols and oversize-response declarations for final review.

<a id="http-operation-matrix"></a>

<a id="concrete-http-contract-draft"></a>

## Concrete HTTP contract draft

**Status:** accepted product boundaries and documented transport drafts. Only the existing human-session, consent and supported use-only grant operations are implemented. Other named models and routes remain unimplemented design contracts. Native backend OpenAPI remains authoritative for delivered symbols.

For example, Alice sets SupportBot's `query` assignment on Support's Pipeline with `canGrant: false` and the reviewed access revision. If the response is lost, her same idempotency key recovers that original assignment result under current authority. Removing that assignment returns a removal result, not `canGrant: false`: the latter still permits use. If SupportBot is subsequently given another grant, replay of Alice's old removal cannot remove it again.

<a id="credential-and-response-profiles"></a>

### Credential and response profiles

Each matrix row selects one of these profiles. This is documentation notation, not a runtime framework or a new credential type.

| Profile | Credential families and local eligibility |
| --- | --- |
| Human session | Kratos cookie or Hydra human access-token bearer. Requires admitted, currently eligible human. Unsupported application family is 401. |
| Application session | HTTP application-key bearer only, with current account/project checks. Unsupported human family is 401. |
| Human administration | Authenticate supported Kratos cookie, Hydra human bearer or HTTP application-key bearer, then require an admitted eligible human and the row's exact authority. A verified application is 403. Cookie writes require CSRF. |
| Invitation activation | Verified Kratos browser cookie plus cookie-write CSRF before local admission. Other credential families are 401. Existing suspension/recovery blocks remain effective. |
| Invitation preview | The same verified Kratos cookie and CSRF boundary before local admission, solely for protected-token scope inspection. Other credential families are 401. Existing suspension/recovery blocks remain effective. No consumption or product authority follows. |
| Own human access | Same supported families as ordinary product operations, but only an eligible human may inspect their own assignments. A verified application is 403. No caller-selected principal. |
| Private recovery | Dedicated service secret only on the private listener. No product credential family or product client operation. |

All HTTP responses use the existing request correlation and problem representation. Sensitive identity/access metadata and secret-bearing responses use `Cache-Control: no-store`. New JSON inputs reject unknown fields and duplicate object keys. Decode bounded UTF-8 JSON, require its declared object shape, and reject duplicate scalar query parameters. GET inputs have no body. Every product mutation requires the existing single bounded `Idempotency-Key`. [Invitation activation](invitation-contracts.md#preview-activation-and-completed-replay) defines its verified-subject binding. Private recovery uses event deduplication instead of that product header.

Declare 400 for competing/malformed authentication, 401 for failed or unsupported credentials, 403 for verified ineligibility/action denial, 404 for missing/hidden resources, 409 for stale revision or idempotency/state conflict, 422 for invalid fields/cursors, and 503 for unconfirmed required dependencies where applicable. New bounded HTTP bodies additionally declare **413**. Preserve the existing generic mapper for 413 and unsupported-media-type 415: `type: about:blank`, `code: http_error`, the standard HTTP status phrase as title, and detail `The request could not be completed.` Do not reflect input or introduce custom exception details. Body bounds are measured on received bytes before decoding/admitting effects. Provider/credential messages never become public problem details.

An unchanged successful PUT or already-completed revocation/removal records a safe original no-change outcome, with the current revision and no re-created assignment. A real access change increments the coordinated access revision once. A replay returns the original status/result, not a freshly executed mutation. Existing published commands retain their own response behavior. New grant results include `operationId`, `accessRevision` and `idempotencyExpiresAt`, except read/session/private-event results and the owner-specific deletion outcome explicitly identified below.

<a id="exact-failure-and-recovery-decisions"></a>

### Exact failure and recovery decisions

| Condition after the applicable visibility/authority checks | Outcome |
| --- | --- |
| Required credential is missing/invalid or wrong family for an identity-specific operation | 401 `http_error`. Applicable trusted challenge, no fallback. |
| Competing/malformed authentication header input | 400 `invalid_authentication_request` before provider I/O. |
| Verified caller is blocked, lacks exact authority, or an application requests human administration | 403 `access_denied`. No hidden-account detail. |
| Target/recipient is missing or hidden under ordinary scope/visibility | 404 `resource_not_found`. A known UUID is not visibility. |
| Unsupported closed action/target/recipient-kind combination or invalid new-model field | 422 `invalid_input` or existing bounded `validation_error` for parsing. No stored unusable grant. |
| Reviewed access revision no longer matches | 409 `stale_revision` on fresh work. Original exact replay is resolved before this check. |
| Same idempotency key, different meaningful request | 409 `idempotency_key_reused`. No second mutation. |
| Same original operation currently reserved/in progress | Existing 409 `idempotency_in_progress` or retained original result after completion. No duplicate attempt. |
| Ordinary removal/demotion would strand authority. Group remains referenced. Key count already two usable. Completed invitation used for a new activation | 409 `conflict`. No partial local effects. |
| Verified recipient/current dependency becomes ineligible before commit | 409 `conflict` under safe disclosure. A caller's own ineligibility remains 403. |
| Required provider state or persistence cannot be confirmed | 503 `dependency_unavailable`. Fail closed, keep any already committed cleanup block. |
| Bounded HTTP request body is too large or media type unsupported | Safe 413/415 `http_error`. No echo, reservation or mutation. |

Invalid/expired/revoked invitation tokens on new activation use the same safe 404 outcome rather than revealing token state or intended resources. The verified recipient is still required. Stale/ineligible issuer assignment intent returns safe 409, with no partial consumption. Secret-bearing response loss returns only the original safe issuance metadata. No plaintext cache or second credential follows. Use [private recovery](private-recovery-handoff.md) for flow/evidence conflicts and [host maintenance](host-maintenance.md) for its separate outcomes.

<a id="full-action-grant-operations"></a>

### Full action-grant operations

For each concrete base below, register three distinct operations: `PUT {base}/grants/{recipient_principal_id}/{action_id}`, `DELETE` at that same route, and `GET {base}/grants`. The table enumerates the symbols, rather than introducing a generic resource registry or catch-all grant endpoint. `action_id` is a catalogue literal appropriate to that target. Colon-containing accepted literals such as `feedback:write` retain their value after normal URL decoding.

| Exact base | PUT / DELETE / GET operation IDs | Result target field and model stem |
| --- | --- | --- |
| `/v1/organizations/{organization_id}` | `setOrganizationActionGrant` / `removeOrganizationActionGrant` / `listOrganizationActionGrants` | `organizationId`. `OrganizationActionGrant` |
| `/v1/projects/{project_id}` | `setProjectActionGrant` / `removeProjectActionGrant` / `listProjectActionGrants` | `projectId`. `ProjectActionGrant` |
| `/v1/projects/{project_id}/access-groups/{access_group_id}` | `setAccessGroupActionGrant` / `removeAccessGroupActionGrant` / `listAccessGroupActionGrants` | `projectId`, `accessGroupId`. `AccessGroupActionGrant` |
| `/v1/projects/{project_id}/application-accounts/{application_principal_id}` | `setApplicationAccountActionGrant` / `removeApplicationAccountActionGrant` / `listApplicationAccountActionGrants` | `projectId`, `applicationPrincipalId`. `ApplicationAccountActionGrant` |
| `/v1/pipelines/{pipeline_id}` | `setPipelineActionGrant` / `removePipelineActionGrant` / `listPipelineActionGrants` | `pipelineId`. `PipelineActionGrant` |
| `/v1/deployments/{deployment_id}` | `setDeploymentActionGrant` / `removeDeploymentActionGrant` / `listDeploymentActionGrants` | `deploymentId`. `DeploymentActionGrant` |
| `/v1/collections/{collection_id}` | `setCollectionActionGrant` / `removeCollectionActionGrant` / `listCollectionActionGrants` | `collectionId`. `CollectionActionGrant` |
| `/v1/sources/{source_id}` | `setSourceActionGrant` / `removeSourceActionGrant` / `listSourceActionGrants` | `sourceId`. `SourceActionGrant` |
| `/v1/model-connections/{model_connection_id}` | `setModelConnectionActionGrant` / `removeModelConnectionActionGrant` / `listModelConnectionActionGrants` | `modelConnectionId`. `ModelConnectionActionGrant` |
| `/v1/processing-profiles/{processing_profile_id}` | `setProcessingProfileActionGrant` / `removeProcessingProfileActionGrant` / `listProcessingProfileActionGrants` | `processingProfileId`. `ProcessingProfileActionGrant` |
| `/v1/embedding-profiles/{embedding_profile_id}` | `setEmbeddingProfileActionGrant` / `removeEmbeddingProfileActionGrant` / `listEmbeddingProfileActionGrants` | `embeddingProfileId`. `EmbeddingProfileActionGrant` |

For each table row, `{Stem}Request` uses exactly `AssignmentInputFields`. `{Stem}Response`, `{Stem}RemovalResponse` and `{Stem}ItemResponse` have the corresponding complete design fields below. Return 201 for a new PUT assignment and 200 for a changed or unchanged existing one. PUT never means removal.

DELETE has no body. It requires one query `expectedAccessRevision` and returns 200, including a currently authorized already-absent result. `removed: true` describes the original post-change absence, not present authority or a grant level. Replay must not remove an assignment created later.

GET requires one `actionId` and ordinary `limit`/`cursor`, returning the existing `PageResponse` shape containing the concrete ItemResponse. Bind exact target and action into the cursor and order by recipient UUID. Every page requires current eligible-human can-use-and-grant authority, scope/membership and applicable last-administrator checks. The existing group-manager alternative permits administration of that group's Add/Update/Delete assignments, not ordinary document use. Applications may receive only eligible use-only actions.

`GET /v1/projects/{project_id}/grant-recipients`, operation `listProjectGrantRecipients`, requires scalar query fields `targetKind`, `targetId` and `actionId`, plus ordinary `limit`/`cursor`. `targetKind` is one of the closed target literals below except `organization`. `targetId` is the corresponding resource/principal UUID. The HTTP boundary converts that pair into the appropriate typed target. For `project`, `targetId` must equal the path Project. For every other kind, load its authoritative parent and require that same Project. Require current caller Project membership/visibility and current can-use-and-grant for the exact target/action, or its existing group-manager document-action authority. Return `PageResponse[GrantRecipientResponse]` with only `principalId`, `displayName`, `kind`, ordered by principal UUID, disclosing only eligible current members of that Project. Bind Project, exact target and action into the cursor. Do not accept JSON/deep-object query targets, a request body, Organization targets or cross-Project targets. This is not an installation directory. Organization recipients are supplied by verified admitted principal ID. No global directory is added.

## Flat response design blocks

**Design notation, not production implementation.** The common names factor identical documented fields for readability only. They create neither a generic endpoint nor an application framework. The named `{Stem}Request` uses the two input fields. Concrete responses below keep each target's fields flat. Their documentary inheritance is not a production class-design requirement. `PageResponse` remains defined in [implemented pagination](../../inframeld-application-contracts/references/pagination.md).

```python
from datetime import datetime
from typing import Literal, TypedDict
from uuid import UUID

# Complete design notation, not runtime classes or a common wire envelope.
# UUID and datetime denote their JSON string representations.
class AccessMutationFields(TypedDict):
    operationId: str  # Nonblank, at most 128 characters.
    accessRevision: int  # Strict integer in the nonnegative signed-BIGINT range.
    idempotencyExpiresAt: datetime  # UTC RFC 3339 on the wire.

class AssignmentInputFields(TypedDict):
    canGrant: bool  # Strict boolean, not an instruction to remove a grant.
    expectedAccessRevision: int

class AssignmentResultFields(AccessMutationFields):
    recipientPrincipalId: UUID
    actionId: str  # Existing catalogue value, valid for this target/kind.
    canGrant: bool
    changed: bool

class RemovalResultFields(AccessMutationFields):
    recipientPrincipalId: UUID
    actionId: str
    removed: Literal[True]
    changed: bool

class GrantItemFields(TypedDict):
    recipientPrincipalId: UUID
    actionId: str
    canGrant: bool


class OrganizationActionGrantResponse(AssignmentResultFields):
    organizationId: UUID

class OrganizationActionGrantRemovalResponse(RemovalResultFields):
    organizationId: UUID

class OrganizationActionGrantItemResponse(GrantItemFields):
    organizationId: UUID


class ProjectActionGrantResponse(AssignmentResultFields):
    projectId: UUID

class ProjectActionGrantRemovalResponse(RemovalResultFields):
    projectId: UUID

class ProjectActionGrantItemResponse(GrantItemFields):
    projectId: UUID


class AccessGroupActionGrantResponse(AssignmentResultFields):
    projectId: UUID
    accessGroupId: UUID

class AccessGroupActionGrantRemovalResponse(RemovalResultFields):
    projectId: UUID
    accessGroupId: UUID

class AccessGroupActionGrantItemResponse(GrantItemFields):
    projectId: UUID
    accessGroupId: UUID


class ApplicationAccountActionGrantResponse(AssignmentResultFields):
    projectId: UUID
    applicationPrincipalId: UUID

class ApplicationAccountActionGrantRemovalResponse(RemovalResultFields):
    projectId: UUID
    applicationPrincipalId: UUID

class ApplicationAccountActionGrantItemResponse(GrantItemFields):
    projectId: UUID
    applicationPrincipalId: UUID


class PipelineActionGrantResponse(AssignmentResultFields):
    pipelineId: UUID

class PipelineActionGrantRemovalResponse(RemovalResultFields):
    pipelineId: UUID

class PipelineActionGrantItemResponse(GrantItemFields):
    pipelineId: UUID


class DeploymentActionGrantResponse(AssignmentResultFields):
    deploymentId: UUID

class DeploymentActionGrantRemovalResponse(RemovalResultFields):
    deploymentId: UUID

class DeploymentActionGrantItemResponse(GrantItemFields):
    deploymentId: UUID


class CollectionActionGrantResponse(AssignmentResultFields):
    collectionId: UUID

class CollectionActionGrantRemovalResponse(RemovalResultFields):
    collectionId: UUID

class CollectionActionGrantItemResponse(GrantItemFields):
    collectionId: UUID


class SourceActionGrantResponse(AssignmentResultFields):
    sourceId: UUID

class SourceActionGrantRemovalResponse(RemovalResultFields):
    sourceId: UUID

class SourceActionGrantItemResponse(GrantItemFields):
    sourceId: UUID


class ModelConnectionActionGrantResponse(AssignmentResultFields):
    modelConnectionId: UUID

class ModelConnectionActionGrantRemovalResponse(RemovalResultFields):
    modelConnectionId: UUID

class ModelConnectionActionGrantItemResponse(GrantItemFields):
    modelConnectionId: UUID


class ProcessingProfileActionGrantResponse(AssignmentResultFields):
    processingProfileId: UUID

class ProcessingProfileActionGrantRemovalResponse(RemovalResultFields):
    processingProfileId: UUID

class ProcessingProfileActionGrantItemResponse(GrantItemFields):
    processingProfileId: UUID


class EmbeddingProfileActionGrantResponse(AssignmentResultFields):
    embeddingProfileId: UUID

class EmbeddingProfileActionGrantRemovalResponse(RemovalResultFields):
    embeddingProfileId: UUID

class EmbeddingProfileActionGrantItemResponse(GrantItemFields):
    embeddingProfileId: UUID


class GrantRecipientResponse(TypedDict):
    principalId: UUID
    displayName: str
    kind: str  # Existing Principal kind vocabulary, not an arbitrary new value.
```

A `ProjectActionGrantResponse` has `projectId` at the top level. Adding a nested `target` object instead would change the contract. A removal is `removed: true`, not `canGrant: false`, because use-only still permits use.

<a id="shared-wire-field-bounds-and-owner-specific-handoffs"></a>

## Shared wire field bounds and owner-specific handoffs

| Field | Draft wire constraint |
| --- | --- |
| Resource/principal/identity IDs | UUID strings converted into their distinct application-owned runtime ID types. Preserve accepted UUID versions/zero values. Only generated key IDs are explicitly UUIDv4. |
| `operationId`, `cleanupOperationId` | Opaque nonblank string, maximum 128 characters. Correlation, not authority. |
| Revisions | JSON bodies require strict integer numbers, 0–9,223,372,036,854,775,807 inclusive. JSON booleans/strings/floats are invalid. Query revisions use one decimal scalar matching `0` or `[1-9][0-9]{0,18}`, parsed within the same range. Reject signs, whitespace, leading zeros, decimal points, exponent notation and duplicate parameters. |
| Boolean fields | Strict JSON boolean. Acknowledgments required by an operation are literal `true`. |
| `name` | Draft new-model bound 1–64 characters with the accepted ASCII selector grammar. Reserved words and migration behavior follow the resource-naming contract. No silent normalization. |
| `displayName` | Draft new-model bound 1–128 Unicode characters, nonblank. Never an identity selector. |
| `reason` | Nonblank safe free text, maximum 512 characters. Never request credentials or private content here. |
| `securityReviewReference`, `operatorLabel` | Nonblank safe text, maximum 128 characters. An audit reference/attribution, not verified authority. |
| Credential input values | Secret-safe values, bounded by the relevant body/token format. Never echoed in validation errors. |
| Times | UTC RFC 3339 timestamps. Lifetime arithmetic and overflow are validated before effects. |
| Pagination | Existing `limit` 1–100, default 25 and `cursor` bound 1024. Feature validates exact scope/action/filter/order. |

All initial-grant result items contain the typed exact `target`, `actionId` and literal `canGrant: true`, without document memberships or fabricated actions. Newly created Project results return its access revision. Their input expected revision protects Organization creation authority. Newly created group/account results return their owning Project access revision. Read and validate each authoritative parent binding before accessing resource-specific grant rows.

Domain-owned Pipeline/configuration/query/Evaluation/model/budget/tracing/feedback payloads retain their existing specification owners. Access supplies fixed exact action/target/principal eligibility and protected transport/replay rules, not replacement domain APIs. Source-derived inspection additionally checks every current protection. An Access grant never overrides those checks.

Project-deletion admission has the following accepted application boundary: input is verified human caller, exact `ProjectId`, `expectedAccessRevision` and original operation identity. Commit block, audit, original result and cleanup obligation together. The semantic result distinguishes admitted/access-blocked, application/key shutdown unfinished, physical cleanup unfinished and complete, as the [existing deletion contract](../../inframeld-knowledge/references/project-deletion.md#project-deletion) requires. Worker cleanup remains bound to that admitted scope even after ordinary membership changes. A retained content-free projection checks the currently eligible original initiating principal and operation binding after membership removal, returns no private inventory/counts/content, and grants no cancellation/continuation. Those owners select its route/schema/retention without selecting a second job enum.

<a id="temporary-grant-operation-inputs"></a>

### Temporary grant operation inputs

`AssignProjectUseOnlyGrantCommand` carries project ID, recipient principal ID, action ID and expected access revision. It requires a whole-number revision of zero or greater and rejects booleans. It does not establish current authority or resource existence. `OperationAdmissionContextDTO` separately carries the idempotency key, method and canonical route. The application service computes the fingerprint from the Command before opening the transaction. Inside that transaction, current authorization of the authenticated principal establishes both organization and project scope. `ProjectActionAuthorizationDTO` carries those two IDs. `ProjectGrantAuthorizationDTO` also carries the current project access revision. Both explicitly implement `AuthorizedOperationScope[ProjectId]` and declare required fields. The generic scope interface also permits organization-scoped work with `project_id=None`. These are observations for the current transaction, not authorization certificates.

`RequestFingerprint` wraps the existing immutable 32-byte HMAC digest, rejects other byte lengths and hides the digest from its representation. `IdempotencyService` unwraps the same bytes at the reservation boundary. The nominal `Command` base and required-field `ProjectCommand` interface add no stored state or execution. [ADR-0066](../../../../docs/adr/ADR-0066-use-typed-operation-contexts-and-command-classification.md) records these input contracts.

These records add no tables or persisted flags. Existing grant, audit and idempotency records retain their schema and values. The [implemented grant chain](../../inframeld-coding-standards/references/services-and-use-cases.md#grant-command-flow) and [ADR-0065](../../../../docs/adr/ADR-0065-application-services-own-write-transactions.md) own orchestration and transaction placement.

Access also owns `ProjectOperationAdmissionRequestDTO`, used by its caller-transaction-bound admission helper. It carries project, method, canonical route, retry key and fingerprint. The helper obtains the actor from authentication and scope from current authorization. Generic admission context, outcomes and reservation persistence remain shared.

## Recipient-directory query shape

**Design notation.** These are scalar query parameters on the concrete Project route, not a JSON body or an Organization directory.

```python
from typing import Literal, NotRequired, TypedDict
from uuid import UUID

class GrantRecipientQuery(TypedDict):
    targetKind: Literal[
        "project", "access-group", "application-account", "pipeline",
        "deployment", "collection", "source", "model-connection",
        "processing-profile", "embedding-profile",
    ]
    targetId: UUID
    actionId: str
    limit: NotRequired[int]  # Existing default 25, maximum 100.
    cursor: NotRequired[str]  # Existing maximum 1024 characters.
```
