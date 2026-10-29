# Recognize a request and recover its original outcome

<a id="recognize-a-request-and-recover-its-original-outcome"></a>

Alice grants Bob permission but loses the response. Repeating the same request key must find the original operation under current authority. It must not apply the grant again or mistake a different request for a retry. [Original-request lookup](operation-recovery-contracts.md#original-request-lookup) separately defines read-only correlation before replay, without a reservation, replacement payload or business execution.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="temporary-operation-outcomes"></a>

### Temporary operation outcomes

`OperationReservationResultDTO` is the low-level reservation adapter's projection. It retains the stored state, optional replay kind and optional expiry. Those fields alone do not establish a valid workflow outcome. `IdempotencyService` validates their combination before constructing one of four frozen, slotted application records:

| Record | Fields and meaning |
| --- | --- |
| `NewOperationReservationDTO` | `operation_id` for newly reserved work. |
| `CompletedSynchronousOperationDTO` | `operation_id`, `created`, a synchronous `replay_kind` and required `expires_at`. |
| `AcceptedAsyncOperationDTO` | `operation_id`, `created` and optional `expires_at`. Asynchronous acceptance is implicit in the type. |
| `RecoveryRequiredOperationDTO` | Original `operation_id` for work requiring recovery. |

For completed and accepted records, `created` distinguishes first completion or acceptance from a saved replay. These records describe operation metadata for this attempt. They are not persisted records or authorization certificates, and add no schema or stored flags. [Jobs and idempotency](#workflow-outcomes) owns conversion failures, retry behavior and the admission helper's shared dependency.

<a id="identify-the-same-request"></a>

<a id="requests"></a>

<a id="3-identify-the-same-request"></a>

## Identify the same request

Every state-changing command requires an opaque **`Idempotency-Key`**, at most **128 characters**. Queries that call a provider need it too, because repeating them can repeat paid work. GET requests do not require this header.

An HTTP command must receive exactly one `Idempotency-Key` header. Duplicate headers are invalid and must be rejected before reserving an operation.

[The accepted Access mutation profile](../../inframeld-access-models/references/grant-contracts.md#mutation-profile) limits new Access-management JSON bodies to 32 KiB and new bulk requests to 100 explicit assignments, with unknown fields rejected in new schemas. It preserves existing published models and does not cap document/configuration payloads. Access uses `expectedAccessRevision`. Domain owners retain their own revisions. Find the original operation before considering a current revision as new work, then apply current authorization to recovery. Creation uses 201, completed metadata changes 200, and durable remaining cleanup 202 through the owning operation's result.

The caller chooses the key to identify this requested operation. It carries no permissions and has no business meaning.

The application recognizes the key together with:

```text
stable authenticated human/application principal
    + organization/project
    + HTTP method and route
    + Idempotency-Key
```

A **principal** is the stable identity of a human or application. Credential IDs are recorded for audit, but changing a key does not create a new principal or make an old request look new.

**Check current identity and permissions before returning a previous outcome.** Remembering the request key cannot bypass a revoked credential or lost document access.

<a id="reserve-the-key-alongside-admission"></a>

### Reserve the key alongside admission

Save the key reservation together with the accepted command. Retain the server-selected original lookup authority family/action atomically with admission. These immutable facts describe the exact current authority a later lookup must check. They are not saved permission. Never replace them on replay or fill missing historical facts from today's request. Only the fixed delivered grant method/route permits deterministic legacy binding backfill. It records the request fingerprint, stable operation or job ID, state, expiry, and safe outcome.

A **canonical request fingerprint** is a consistent summary of the meaningful input. Equivalent requests produce the same fingerprint. Reusing a key with different input produces a conflict.

For uploads, use the validated file bytes and fields that affect meaning. Ignore multipart boundaries, which only format the HTTP upload and can differ between equivalent requests.

Hold uploads in private temporary storage with resource limits before accepting them. Delete an unaccepted upload only when its ownership is positively known. Looking unused is not enough.

<a id="fingerprint-secret-bearing-requests-without-exposing-the-secret"></a>

### Fingerprint secret-bearing requests without exposing the secret

Requests containing secrets need a **keyed HMAC fingerprint**. This is a hash calculated with a separately protected deployment key. **Domain separation** labels its purpose so the same fingerprint cannot be confused with another use of HMAC.

Do not save raw request bodies or ordinary, unkeyed hashes of easily guessed secrets in retry records. An attacker could guess a weak secret and compare hashes. Use the selected keyed fingerprint instead.

Keep the fingerprint key stable for the whole retention period and include it in protected recovery of the installation.

Changing a submitted credential must produce a conflicting fingerprint even when every non-secret field remains identical.

<a id="return-the-documented-outcome-instead-of-starting-duplicate-work"></a>

### Return the documented outcome instead of starting duplicate work

After checking current authentication and authorization, apply the following response contract:

| Retry condition | Response |
| --- | --- |
| **Same key and equivalent request. Safe result complete** | Replay the documented safe outcome without another mutation. An accepted asynchronous command follows the dedicated `202` rule below. |
| **Same key, different request** | `409 idempotency_key_reused`. |
| **Same key for an unfinished synchronous command or query** | `409 idempotency_in_progress`, the operation identity, and a useful `Retry-After` header. |
| **External outcome uncertain, with no proven safe replay** | The operation’s stable `recovery_required` status. No automatic redispatch. |
| **Same accepted asynchronous command** | The same `202 Accepted`, job identity, and `Location` header. |

A **synchronous** operation returns its result in that request. An **asynchronous** operation returns a job to follow while work continues. `Location` identifies the job, and `Retry-After` says when to check again.

Once an asynchronous command is accepted, its retries return the original **`202`**, even if the job is now complete, failed, or uncertain. A running background job does not turn that retry into `409 idempotency_in_progress`.

Read the job resource for current progress and outcome. Safe vector-write retries remain attempts inside that same job.

Client libraries must reuse the original key and honor `Retry-After`. ModelGateway also controls provider-library retries, so a library cannot silently repeat a paid call underneath the application's own retry policy.

<a id="reservation-inputs"></a>

<a id="supply-retry-metadata-and-trusted-scope"></a>

### Supply retry metadata and trusted scope

Alice's Command names the project and the grant she wants to assign. Her verified caller identity and current authorized scope come from separate checks. Pass these existing objects to [`OperationIdempotency.find_or_reserve()`](../../../../apps/backend/src/inframeld_backend/shared/application/protocols/operation_idempotency.py). All five arguments are required and keyword-only:

| Argument | Source and meaning |
| --- | --- |
| `context: OperationAdmissionContextDTO` | Retry key, method and canonical route from the entry point. It carries no authority. |
| `access: AccessContextDTO` | Authenticated actor identity, rather than the grant recipient. |
| `authorization: AuthorizedOperationScope[ProjectScope]` | Organization and project scope established by current authorization. Project results use `ProjectId`. Organization-scoped results supply `None`. |
| `fingerprint: RequestFingerprint` | Immutable 32-byte digest already computed by the owning workflow. |
| `expected_replay_kind: OperationReplayKind` | Replay category required by the owning operation. |

[`IdempotencyService`](../../../../apps/backend/src/inframeld_backend/shared/application/services/idempotency_service.py) constructs `OperationReservationRequestDTO` at the reservation-writer boundary. It reads the actor from access, both scope IDs from authorization, retry metadata from context and digest bytes from `fingerprint.value`. It copies these values exactly, without normalization, scope inference or fingerprint recomputation. The Command is not an idempotency input. The owning workflow also supplies its immutable original lookup authority separately. The grant service supplies Project grant-read for its fixed action. The Project admission helper supplies Project action-use for its explicit action. Organization callers supply an accepted Organization action-use binding. Shared idempotency preserves that server-selected binding and rejects incompatible retry metadata without changing original request identity, fingerprints, expiry or outcomes.

`AuthorizedOperationScope` is a field-based Protocol parameterized by the project type. This keeps a project-specific DTO's `project_id: ProjectId` precise while allowing organization scope through the same generic method. Concrete DTOs explicitly implement the interface and declare their own fields. Frozen records remain immutable, but the Protocol itself does not express read-only access. Neither interface conformance nor a typed fingerprint proves permission. Authorize current state first on every attempt, including replay.

The grant workflow first verifies that authorization returned the project requested by its Command. It does this before lookup on every attempt, including replay. A mismatch is an internal runtime error and rolls back, without returning a saved response or making a reservation. After matching, it takes scope from authorization for both reservation and membership repository loading. The Command stays unchanged and continues supplying the requested grant details. The grant workflow passes its context directly and owns the transaction. The admission-only helper retains its public request input and caller-owned transaction. It calls the action family with `ProjectActionAuthorizationRequestDTO`, then checks that the returned project matches its input before any idempotency lookup or replay. A mismatch raises an internal runtime error, leaving rollback to the caller. After matching it converts the input's method, route and key into the admission context. Both consumers share mapping and outcome validation. [ADR-0066](../../../../docs/adr/ADR-0066-use-typed-operation-contexts-and-command-classification.md) records the idempotency inputs. [ADR-0067](../../../../docs/adr/ADR-0067-standardize-authorization-capabilities-with-typed-requests.md) standardizes `require_authorization(access, request)` across the two permission families. Authorization requests remain separate from retry metadata, fingerprints and expected revisions. Neither convention introduces a dispatcher.

For new grant work, the service checks the expected project revision, loads the recipient's existing membership in authorization scope, validates the returned target, invokes its domain assignment and saves through `ProjectMembershipRepository`. It passes the original operation ID for audit correlation and the checked project-wide revision for persistence. Replays return before this load, so they cannot add another grant, revision or audit. Required completion metadata still commits in the same application-owned transaction. The repository's private value snapshots live only for that transaction and are discarded after failure or transaction end. [ADR-0068](../../../../docs/adr/ADR-0068-model-project-grants-through-project-membership-aggregates.md) changes the grant persistence boundary without changing retry identity, fingerprints, expiry or outcome validation.

<a id="workflow-outcomes"></a>

<a id="use-distinct-workflow-outcomes"></a>

### Use distinct workflow outcomes

Alice's first request receives a new reservation and may change the grant. Her retry receives completed metadata and must not make that change again. Application services distinguish those paths by their result types:

| Outcome | What the owning workflow may do |
| --- | --- |
| `NewOperationReservationDTO` | Execute newly reserved work using its operation ID. |
| `CompletedSynchronousOperationDTO` | Return the recorded synchronous outcome. It carries the operation ID, recognized non-asynchronous replay kind and required stored expiry. |
| `AcceptedAsyncOperationDTO` | Report acceptance of the original asynchronous operation. Preserve its optional stored expiry. Acceptance does not prove successful background execution. |
| `RecoveryRequiredOperationDTO` | Handle uncertainty about the original operation. Its ID is preserved and work must not restart automatically. |

Completed and accepted outcomes include `created` to distinguish first completion or acceptance from replay. Newness and recovery are represented by their own classes. These records carry operation metadata, not permission. Every attempt still checks current authorization before looking up a reservation.

The low-level writer retains `OperationReservationResultDTO` as its storage projection. `IdempotencyService` is the conversion boundary. A new reservation must have the in-progress shape without completion metadata. Existing in-progress work raises the same error with the original operation ID and three-second retry advice. Recovery-required work cannot carry completion metadata. Completed work must match the caller's required `expected_replay_kind`. Synchronous completion requires a stored expiry, while asynchronous acceptance preserves its optional expiry. Malformed or incompatible results raise the existing conflict error.

Only a `NewOperationReservationDTO` can be passed to `record_completed_result()`. The owner saves its effects first in the same transaction. Completion returns either synchronous completed metadata or asynchronous acceptance. For the grant command, recovery-required or unexpected asynchronous outcomes conflict before commit. An authorized synchronous replay returns without another grant, revision increment or audit event.

Access owns [`ProjectOperationAdmissionService`](../../../../apps/backend/src/inframeld_backend/access/application/services/project_operation_admission_service.py) and its request DTO. The helper first authorizes the action and matches the returned project, then delegates with the caller's expected replay kind. The principal comes from authentication and both scope IDs from authorization. Its caller continues owning the transaction. Generic idempotency, outcomes and reservation persistence remain shared. [PostgreSQL admission tests](../../../../apps/backend/tests/integration/idempotency/test_authorized_replay_postgres.py) exercise replay metadata and rollback through the real reservation adapter. This verifies shared retry decisions, not another complete product command or job lifecycle.

The grant route exercises the safe-result path. The in-progress, asynchronous `202`, uncertain, issued-secret, and answer-receipt outcomes above retain their separate contracts. Their owning workflows still need implementation where noted.

<a id="protect-competing-edits-and-retained-history"></a>

<a id="revisions"></a>

<a id="6-protect-competing-edits-and-retained-history"></a>

## Protect competing edits and retained history

Idempotency prevents duplicate execution of one requested action. It does not resolve two different actions that compete to change the same state.

Alice and Bob both try to promote Deployment revision **12**, using different idempotency keys. These are two competing decisions:

| Command | Result |
| --- | --- |
| **First conditional update against revision 12** | Succeeds and advances the Deployment to revision **13**. |
| **Second conditional update against revision 12** | Updates zero rows because revision 12 is no longer current. Returns **`409 stale_revision`**. |

Each protection answers a different question: the idempotency key identifies a repeated request, the revision detects another person's intervening change, and the fence proves which worker attempt may save the result.

<a id="limit-guarantees-to-retained-authoritative-history"></a>

### Limit guarantees to retained, authoritative history

Keep completed duplicate-detection records for **at least 24 hours** and for as long as their work remains active. Publish their expiry time. After expiry, the server no longer promises to recognize that old request.

The implemented project-grant response publishes the stored deadline as `idempotencyExpiresAt`. An authorized replay returns that same timestamp. Retrying does not extend the retention window. The deadline limits duplicate detection. It does not delete the grant.

A new idempotency key always identifies a new requested operation, even when its input equals a previous request. Clients must not generate new keys merely because the original response was lost.
