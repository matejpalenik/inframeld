# Exact-target grant transport contracts

Alice changes Bob’s permission on one resource. The request identifies that resource through its concrete route, with reviewed state and original operation identity. These contracts do not introduce a generic grant endpoint.

<a id="mutation-profile"></a>

<a id="bounded-access-mutation-profile"></a>

## Bounded Access mutation profile

New Access-management JSON bodies are limited to **32 KiB (32,768 bytes)**. New bulk assignment requests carry at most **100 explicit assignments**. Reject unknown fields in new request schemas. These limits do not apply to document uploads or complete domain configuration payloads. Preserve existing published schema names, field behavior and restrictions rather than silently tightening them through a shared replacement model.

Use camelCase wire fields, UUID strings for known resource identities, an opaque string `operationId`, UTC timestamps and strictly nonnegative integer revisions within the [shared exact numeric range](../../inframeld-application-contracts/references/http-mcp-and-generated-clients.md#numeric-revisions). Access writes carry `expectedAccessRevision`. Other owners retain their domain-specific revision inputs. Every mutation carries exactly one `Idempotency-Key`, at most 128 characters. The original operation is found before treating today's revision as a new write, with current authentication/authorization still required to recover it. [Jobs and idempotency](../../inframeld-application-contracts/references/idempotency-and-replay.md#requests) own request identity and recovery.

A local change saves its domain effects, revision, audit and original outcome together. Use 201 for creation, 200 for completed metadata changes and 202 when durable cleanup remains. Return the original operation identity, appropriate resource identity, committed revision and safe outcome through the owning operation's typed result. A 202 response means accepted work, not completed erasure. This profile does not introduce a generic operation envelope or command framework. The [concrete contracts and future-resource drafts](#http-operation-matrix) distinguish current native symbols from contracts awaiting their real resource producers.

<a id="http-operation-matrix"></a>

<a id="concrete-http-contract-draft"></a>

## Concrete contracts and future-resource drafts

**Status:** Organization, Project, access-group and application-account exact grant GET/PUT/DELETE, both own-access reads and Project-scoped eligible-recipient discovery are implemented. The retired use-only POST is absent from native OpenAPI and generated clients. Native OpenAPI remains authoritative for implemented symbols. Other resource-target routes in this reference remain accepted design contracts for their real owners. Automated platform qualification and deferred human acceptance are separate evidence, not consequences of this status paragraph. Human routes use cookie or Hydra bearer authentication, without adding application-key authentication.

For example, Alice sets SupportBot's `query` assignment on Support's Pipeline with `canGrant: false` and the reviewed access revision. If the response is lost, her same idempotency key recovers that original assignment result under current authority. Removing that assignment returns a removal result, not `canGrant: false`: the latter still permits use. If SupportBot is subsequently given another grant, replay of Alice's old removal cannot remove it again.

<a id="ordinary-project-creation"></a>

### Implemented ordinary Project creation

Alice already belongs to the installation and wants a separate Production Project. `GET /v1/my-organization-access` returns her actual Organization ID, principal ID, current Organization Access revision and stored Organization grants. The read requires current admitted-human eligibility, not `create-projects`. It can return an empty array. It takes no principal selector and reveals no other person's grants or installation inventory.

`POST /v1/projects` requires current human `create-projects` on that Organization. [The request model](../../../../apps/backend/src/inframeld_backend/access/http/requests/project_creation_request.py) takes `organizationId`, `expectedAccessRevision`, `name` and `displayName`. The revision is the reviewed Organization revision, not a Project metadata revision. A successful creation leaves the Organization revision unchanged and returns HTTP `201`. The new Project starts at Access revision `1` and metadata revision `0`.

The service commits the Project, creator membership, [eighteen explicit initial assignments](actions-and-initial-grants.md#initial-project-grants), audit and original outcome together. Name conflicts and stale fresh-write revisions leave no partial creation. Cookie writes require trusted Origin and `X-Inframeld-CSRF: 1`. Both routes return `Cache-Control: no-store`. Creation uses the existing single idempotency header and bounded JSON contract.

The [creation response](../../../../apps/backend/src/inframeld_backend/access/http/responses/project_creation_response.py) contains the original operation identity/deadline, Organization/Project IDs, submitted names, initial Project revisions and `initialGrants`. This receipt is immutable history, not present permissions or metadata. Exact replay requires current eligibility and `create-projects`, then returns the original receipt before checking a fresh-write expected revision. Replay neither restores removed grants nor reverses later renames. Preserve the original key and complete request after uncertain output.

[The user guide](../../../../apps/docs/src/app/guides/create-project/page.mdx) gives the supported API/client task. There is no CLI creation command, starter provisioning or RAG resource creation in this operation. [Human qualification #313](https://github.com/matejpalenik/inframeld/issues/313) remains unready for handoff until the chosen supported authentication procedure and disposable setup/cleanup are complete. Provider fixtures do not supply user credentials. First-use/setup qualification remains #185 and metadata-repair qualification remains #298.

<a id="project-membership-changes"></a>

### Implemented Project membership changes

[`addProjectMember` and `removeProjectMember`](memberships-groups-and-handover.md#change-project-membership) share `/v1/projects/{project_id}/members/{principal_id}`. PUT uses `ProjectMembershipRequest` with only strict integer `expectedAccessRevision`. DELETE has no body and requires that same revision as one scalar query field. Reject duplicate or unknown query fields, unknown or duplicate JSON fields, boolean revisions and revisions outside 0–9,007,199,254,740,991. PUT uses the bounded JSON and 413/415 profile. Both require one nonblank, at-most-128-character `Idempotency-Key`, ordinary human authentication and cookie-write CSRF where applicable.

`ProjectMembershipResponse` and `ProjectMembershipRemovalResponse` contain the original `operationId`, `idempotencyExpiresAt`, `projectId`, `principalId`, `accessRevision`, `changed` and literal `member: true` or `removed: true`. Changed PUT is 201, unchanged PUT is 200 and DELETE is 200. The existing 400/401/403/404/409/422/503 problems apply. Every response is no-store. Current eligibility, Project visibility/membership and use of `manage-project-members` precede reservation and replay. Stale review is checked only for fresh work. The [original receipt](access-lifecycle-persistence.md#project-membership-original-results) preserves original status and outcome independently of a later membership change.

<a id="project-action-grant-read"></a>

### Implemented Project action-grant read

[`listProjectActionGrants`](../../../../apps/backend/src/inframeld_backend/access/http/routes/project_action_grant_routes.py) uses `GET /v1/projects/{project_id}/grants`. Require one supported Project `actionId`, with ordinary `limit` and `cursor`. Reject request bodies, duplicate scalar query fields and unknown query fields. There is no expected revision or idempotency key. The [response item](../../../../apps/backend/src/inframeld_backend/access/http/responses/project_action_grant_item_response.py) has flat `projectId`, `recipientPrincipalId`, `actionId` and `canGrant` fields. The shared `PageResponse` carries only `items` and nullable `nextCursor`, without totals or an Access revision.

Every page requires current admitted-human eligibility, Project visibility/membership and use plus grant authority for that exact action. Recovery blocks and current OAuth credential evidence retain their ordinary effects. A Project action read has no group-manager alternative. Stored suspended-recipient assignments remain visible. Results do not expand implied permissions or discover eligible recipients. Cursors bind installation, Organization, Project, action and recipient-ID order, without becoming authorization or snapshots. All responses are no-store. [The guide](../../../../apps/docs/src/app/guides/list-project-action-grants/page.mdx) explains the caller's setup and continuation.

This GET retains its original meaning. Organization, group and application-account readers provide the same bounded stored-assignment view for their exact target and supported action. Group managers may additionally administer document-action assignments on their own group. Generic original-operation lookup still requires current exact eligible-human use-and-grant in every family, including groups.

<a id="implemented-project-grant-administration"></a>

### Project own-access and grant changes in the current candidate

[`getMyProjectAccess`](../../../../apps/backend/src/inframeld_backend/access/http/routes/my_project_access_routes.py) uses `GET /v1/projects/{project_id}/my-access`. A current eligible human Project member can read their own stored Project, access-group and application-account grants, group memberships and group managements, together with the current Project Access revision. No action-administration grant is required. One bounded page and cursor cover all those relationships, with current authorization on every page. There is no caller-selected principal, eligible-recipient directory or effective-permission expansion.

[`setProjectActionGrant` and `removeProjectActionGrant`](../../../../apps/backend/src/inframeld_backend/access/http/routes/project_action_grant_change_routes.py) implement PUT/DELETE at `/v1/projects/{project_id}/grants/{recipient_principal_id}/{action_id}` for all eighteen Project actions. PUT uses strict `canGrant` and `expectedAccessRevision` JSON fields. DELETE has no body and requires one canonical `expectedAccessRevision` query field. Both require the single idempotency key and current human use-and-grant authority for the exact Project/action. New assignments return 201, while existing-assignment changes, no-ops and removals return 200. The saved original receipt preserves its status, revision, outcome and expiry. Current authority is checked before replay, and replay cannot reapply an assignment or remove a later one.

The [assignment guide](../../../../apps/docs/src/app/guides/assign-project-grant/page.mdx) explains revision discovery, eligible recipients, safe departure and original-result recovery, including read-only retained historical POST lookup. Source and PostgreSQL evidence establish the inspected backend boundaries. Native SDK/runtime/platform checks remain separately qualified, and [human qualification #336](https://github.com/matejpalenik/inframeld/issues/336) is not claimed complete. The owning [#226](https://github.com/matejpalenik/inframeld/issues/226) tracks complete implementation and automated acceptance separately from human qualification.

<a id="grant-delivery-boundary-and-cutover"></a>

### Grant delivery boundary and selected cutover

[ADR-0128](../../../../docs/adr/ADR-0128-consolidate-exact-target-grant-mutations.md) selects complete Organization, Project, access-group and application-account administration for #226, with own-access reads and eligible-recipient discovery for those Project-scoped targets. The target catalogue below retains every accepted resource variant. Each other resource feature supplies its actual target tables, target-specific GET/PUT/DELETE and eligible-recipient integration under Access's rules when delivering that feature. Future target integration remains required v1 work with those owners. No generic registry or placeholder table is needed to close Access-owned administration.

The implemented Project mutation interface is `PUT /v1/projects/{project_id}/grants/{recipient_principal_id}/{action_id}` and DELETE at the same path. The live POST route now returns 405. `assignProjectUseOnlyGrant` and its creation-only request/response exports are removed from native OpenAPI and all three generated clients. Actual callers and fixtures use explicit exact PUT intent. GET and the existing PUT/DELETE operation IDs and meanings remain unchanged.

The historical POST rejected an existing assignment. PUT can change it, including downgrading use-and-grant to use-only. Never redirect or automatically convert an original POST retry into PUT. Preserve retained original operation identity, method, canonical route, fingerprint, expiry and outcome without extending retention. Original-operation lookup remains read-only and checks current authority for the original exact Project/action. Route removal cannot convert an uncertain or expired original result into proof of failure or permission to dispatch a new write.

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

When delivering each concrete target below, register three distinct operations: `PUT {base}/grants/{recipient_principal_id}/{action_id}`, `DELETE` at that same route, and `GET {base}/grants`. The [delivery boundary](#grant-delivery-boundary-and-cutover) assigns Access-owned and resource-feature implementation. The table enumerates the symbols, rather than introducing a generic resource registry or catch-all grant endpoint. `action_id` is a catalogue literal appropriate to that target. Colon-containing accepted literals such as `feedback:write` retain their value after normal URL decoding.

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
    accessRevision: int  # Strict integer from 0 through 9,007,199,254,740,991.
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
| Revisions | Follow the [shared numeric revision contract](../../inframeld-application-contracts/references/http-mcp-and-generated-clients.md#numeric-revisions): strict JSON integer numbers, 0–9,007,199,254,740,991 inclusive. JSON booleans/strings/floats are invalid. Query revisions use one decimal scalar matching `0` or `[1-9][0-9]{0,15}`, parsed within the same range. Reject signs, whitespace, leading zeros, decimal points, exponent notation and duplicate parameters. |
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

Project-deletion admission has the following accepted application boundary: input is verified human caller, exact `ProjectId`, `expectedAccessRevision` and original operation identity. Commit block, audit, original result and cleanup obligation together. The semantic result distinguishes admitted/access-blocked, application/key shutdown unfinished, physical cleanup unfinished and complete, as the [existing deletion contract](../../inframeld-knowledge/references/project-deletion.md#project-deletion) requires. Worker cleanup remains bound to that admitted scope even after ordinary membership changes. A retained content-free projection checks the currently eligible original initiating principal and operation binding after membership removal, returns no private inventory/counts/content, and grants no cancellation/continuation. The [logical deletion projection](../../inframeld-application-contracts/references/operation-recovery-contracts.md#deletion-status-inspection) now defines its accepted facts without a second job enum. The implemented `GET /v1/deletions/status` reader uses the current human and original operation binding without restoring membership. An eligible noninitiator gets the same `200` unresolved object as missing or expired history, while credential/current-eligibility failures retain their existing errors. The [owning recovery contract](../../inframeld-application-contracts/references/operation-recovery-contracts.md#implemented-content-free-reader) records the delivered nullable facts and captured retention. This read does not implement Delete-project admission, application/key shutdown or physical cleanup.

<a id="temporary-grant-operation-inputs"></a>

### Ephemeral typed grant operation inputs

`SetProjectActionGrantCommand` carries Project ID, recipient principal ID, action ID, explicit boolean `can_grant` and expected Access revision. The corresponding removal Command omits the level because removal and use-only are distinct. It requires a whole-number revision of zero or greater and rejects booleans. It does not establish current authority or resource existence. `IdempotencyContextDTO` separately carries the idempotency key, method and canonical route. The application service computes the fingerprint from the Command before opening the transaction. Inside that transaction, current authorization of the authenticated principal establishes both organization and project scope. `ProjectActionAuthorizationDTO` carries those two IDs. `ProjectGrantAuthorizationDTO` also carries the current project access revision. Both explicitly implement `AuthorizedOperationScope[ProjectId]` and declare required fields. The generic scope interface also permits organization-scoped work with `project_id=None`. These are observations for the current transaction, not authorization certificates.

`RequestFingerprint` wraps the existing immutable 32-byte HMAC digest, rejects other byte lengths and hides the digest from its representation. `IdempotencyService` unwraps the same bytes at the reservation boundary. The nominal `Command` base and required-field `ProjectCommand` interface add no stored state or execution. [ADR-0066](../../../../docs/adr/ADR-0066-use-typed-operation-contexts-and-command-classification.md) records these input contracts.

These records add no tables or persisted flags. Existing grant, audit and idempotency records retain their schema and values. The [implemented grant chain](../../inframeld-python-standards/references/services-and-use-cases.md#grant-command-flow) and [ADR-0065](../../../../docs/adr/ADR-0065-application-services-own-write-transactions.md) own orchestration and transaction placement.

Access also owns `ProjectOperationAdmissionRequestDTO`, used by its caller-transaction-bound admission helper. It carries project, method, canonical route, retry key and fingerprint. The helper obtains the actor from authentication and scope from current authorization. Generic idempotency context, outcomes and reservation persistence remain shared.

## Recipient-directory query shape

**Implemented Access boundary:** `listProjectGrantRecipients` accepts only `project`, `access-group` and `application-account`. Native `GrantTargetKind` owns these three dashed values. Eligibility is filtered before the bounded page limit. Organization recipients use verified admitted human IDs, with no Organization directory. The following design notation also retains future variants for their real feature owners. Those variants are not admitted by the current route.

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
