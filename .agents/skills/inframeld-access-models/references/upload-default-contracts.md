# Inspect and change future-upload defaults

<a id="inspect-and-change-upload-defaults"></a>

Alice manages Support and wants future uploads to use HRPrivate instead of SupportKnowledge. She reads the saved audience and Project Access revision, then submits the complete replacement with that reviewed revision and an original-request key. Existing Documents keep their audiences.

Access owns this saved configuration, current authority checks and immutable original receipt. The HTTP/SQL implementation and generated public operations exist. Native-client conformance and platform qualification are separate checks. Knowledge upload admission remains a receiving integration in #41, the administration journey remains in #264, and starter provisioning remains in #349.

| Reader question | Owning section |
| --- | --- |
| What can be read or changed? | [Native HTTP contract](#native-http-contract) |
| Which permissions must still exist? | [Current authority](#current-authority) |
| What happens after a lost response or later edit? | [Recover the exact original](#recover-exact-original) |
| What does upload admission consume? | [Persistence and admission boundaries](#persistence-and-admission-boundaries) |

<a id="native-http-contract"></a>

## Native HTTP contract

Both operations address exactly `/v1/projects/{project_id}/upload-defaults`. [Native OpenAPI](../../../../contracts/openapi/v1/inframeld-v1.json) and the [request model](../../../../apps/backend/src/inframeld_backend/access/http/requests/project_upload_default_request.py) own the delivered fields.

| Operation | Input and result |
| --- | --- |
| GET, `getProjectUploadDefaults` | No query or body. `ProjectUploadDefaultResponse` contains `projectId`, `accessRevision` and required `groupIds`. A valid Project with no saved links returns `groupIds: null`. Missing or foreign scope is not an unconfigured Project. |
| PUT, `setProjectUploadDefaults` | Required `Idempotency-Key`, `groupIds` and `expectedAccessRevision`. The complete audience is nonempty, contains no duplicates and belongs to this Project. A 200 `ProjectUploadDefaultChangeResponse` contains the resulting group IDs and revision plus `operationId` and `idempotencyExpiresAt`. |

Reads and receipts use ascending group UUIDs. Input order does not change the set's meaning. There is no public clear-to-null operation. Reject unknown fields, duplicate JSON properties, invalid UUIDs, null or empty writes, and boolean, noninteger, negative or unsafe revisions. JSON input is bounded to 32 KiB. Existing ProblemDetails cover invalid input, hidden scope, denied access, stale revisions, conflicts and unavailable dependencies. Protected successes and failures are noncacheable.

Cookie writes require the configured Origin and CSRF marker. Human bearers use ordinary product authentication without cookie CSRF. A verified application remains denied at this human-only operation. Authentication never replaces current eligibility and permission checks.

<a id="current-authority"></a>

## Current authority

GET requires a currently eligible human, current Project membership, exact `manage-upload-defaults` use authority and ordinary membership plus management of every currently saved group. An unconfigured Project still requires the actor, scope and exact action checks. No wildcard, delegation level or unrelated Project action supplies this authority.

PUT additionally requires current management of every proposed group, including groups retained in both sets. Validate the complete same-Project set instead of filtering missing or foreign groups. Suspended principals, pending recovery and stale credentials cannot inspect or change the configuration. Unknown or incoherent facts fail closed.

The [service](../../../../apps/backend/src/inframeld_backend/access/application/services/project_upload_default_service.py) authorizes before original-result recovery. Fresh work checks the reviewed Project revision before comparing equal sets. A fresh equal-set no-op preserves revision and adds no change audit, but saves its safe original receipt and completion. A stale equal-set request conflicts.

<a id="recover-exact-original"></a>

## Recover the exact original

Suppose Alice changed A to B, lost the response, and someone later selected C. She repeats the original PUT with the same caller, Project, body, reviewed revision and original-request key. Access checks current management of C and submitted B before reading history. Management of historical A is unnecessary unless it is also in C or B.

An authentic original is recovered before a fresh revision check. Its public receipt describes B and its original revision, operation ID and replay deadline. It never exposes the private before audience A and never reapplies B over C. A current GET describes C. Losing management of C or B denies recovery before history is disclosed.

Keep the original deadline unchanged. Expired or unavailable recovery cannot authorize a blind replacement. A known rollback differs from uncertain COMMIT or response delivery. Neither client nor server automatically redispatches the change or mints a replacement key after uncertainty.

<a id="persistence-and-admission-boundaries"></a>

## Persistence and admission boundaries

[Migration 0030](../../../../apps/backend/migrations/versions/0030_project_upload_defaults.py) implements scoped group links and safe original rows. Zero links mean unconfigured. The Project owns the Access revision. Live links have restrictive same-scope foreign keys to real groups, so deleting an in-use group conflicts until an authorized replacement removes its reference. Historical receipts do not pin removable groups.

Use the existing short caller-owned READ COMMITTED transaction and Organization-to-Project coordination. Refresh facts after waiting. Save the complete replacement, one revision increment, one change audit, safe original and shared completion together. Rollback preserves the previous set and removes new effects. The [persistence reference](access-persistence.md#project-upload-defaults) owns exact row and retention boundaries.

The Access-owned `ProjectUploadAudienceReader` supplies the saved set and Project revision inside the receiving admission transaction. It requires valid exact scope and fresh coordinated reads, not administration GET permission. This projection is an observation, never authorization. #41 independently rechecks actor, credential, Project and Add documents authority on every effective group, then retains the admitted audience. Missing, foreign, unavailable or unauthorized groups block admission without fallback. Document storage, source sync, retrieval and starter creation remain with their owning features.
