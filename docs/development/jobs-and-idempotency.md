# Background jobs, retries, and competing changes

Alice starts a Support build, but the response never reaches her browser. Sending the same request again should find that build, not start another. This guide explains how saved work survives interruptions and how the application tells a retry from a new decision.

[Application structure](application-structure.md) explains which module owns the work. The [supporting records](data-model.md#supporting-records) define jobs, attempts, request reservations, and their IDs.

Start with the worker's normal flow, then compare a lost model response with a safe storage retry. Later sections cover keys, receipts, competing edits, and restoration.

> **Implementation status:** Scoped PostgreSQL reservations and the first Access project-grant command are implemented with focused tests. Worker execution, issued-secret and answer-receipt responses, and default-route resolution remain accepted design awaiting their owning workflows.

## Contents

| Reader’s question | Start here |
| --- | --- |
| Does a failed CLI invocation mean I can start again? | [Automation and original admission](#automation-recovery) |
| What does continuing a partial import mean? | [Original import and child outcomes](#import-recovery) |
| What if identity cleanup or project deletion is interrupted? | [Identity cleanup](#identity-cleanup) and [project deletion](#project-deletion) |
| What survives an interrupted worker? | [1. Admit work and claim an attempt](#admission) |
| May a timed-out operation run again? | [2. Separate safe retries from uncertain work](#uncertain) |
| What does the idempotency key mean? | [3. Identify the same request](#requests) |
| Can a lost key-creation response reveal the key? | [4. Recover secret operations safely](#secrets) |
| Why does a retry contain no answer text? | [5. Recover an answer through its receipt](#answers) |
| How is a new change different from a retry? | [6. Protect competing edits and retained history](#revisions) |
| Can a late job regain release authority? | [7. Reuse these rules for automatic publication](#automatic) |
| Which interruption points need testing? | [8. Maintainer checks](#maintainer-checks) |
| Why these choices, and what remains open? | [9. Decision and reference map](#decision-map) |

<a id="admission"></a>

## 1. Admit work and claim an attempt

When the API accepts work, it saves that decision before reporting success. This is **admission**. One database transaction saves the job, the record used to recognize retries, any already-known business IDs, and required audit information. Either all are saved or none are, so accepted work cannot lose its job or duplicate check.

Some IDs are discovered later. A source-sync job can find a document, create its records through the normal application command, then do the associated external work. The original HTTP request need not discover a million S3 objects before starting the sync.

### One worker owns the supported queue

One worker polls PostgreSQL for eligible jobs. For each claim, it:

1. **Claim one eligible job.** In a short transaction, lock the job and save the attempt, worker, expiry, and ownership token. Then finish the transaction.
2. **Do the work.** Process files and call external services without keeping that SQL transaction open.
3. **Save progress or completion only while still the owner.** Each save must present the current ownership token.

The time-limited claim is a **lease**. Its ownership token is a **fence**. If a replacement attempt takes over, PostgreSQL rejects writes carrying the old token. A late result from the old worker cannot become the application's current result.

An attempt that loses ownership is **stale**. Finishing its computation does not give it permission to publish database state.

### Keep queue infrastructure proportionate to one server

PostgreSQL is also the queue for the single-server deployment. Index the status and next-attempt fields used to find jobs. Limit the queue size and simultaneous work, and monitor how long the oldest job has waited.

V1 needs no SQS, Kafka, Redis, dead-letter queue, or workflow engine. Webhooks are deferred. A future delivery queue or **outbox**, a record of notifications waiting to be sent, can be added when delivery requires it. Having a `WebhookDispatcher` interface is not a reason to add unused infrastructure.

```mermaid
sequenceDiagram
    participant API
    participant DB as PostgreSQL
    participant Worker
    participant Remote as External dependency
    API->>DB: Commit job, request reservation, and audit
    Worker->>DB: Claim bounded attempt and fence
    Worker->>Remote: Perform work outside SQL transaction
    Worker->>DB: Save progress only if fence still matches
```

The arrows show calls. The fence protects database progress and publication. It cannot cancel a request that an external service has already accepted.

### Checkpoints, cancellation, and safe resume

Save progress between limited-size files, batches, or evaluation cases. Retry automatically only when work was definitely not sent or repeating it is known to be safe. Wait between retries with bounded backoff and allow **at most three application attempts**. Once the budget is exhausted, record `failed` with that reason. There is no `paused` job state.

### Apply the same jobs to Ragas work

For example, a starter-generation job may save 17 usable drafts before a provider fails. Preserve those drafts and per-unit outcomes; reopening progress or review must not repeat completed calls. [Evaluation](evaluation.md#generation) owns generation/review semantics, while this guide owns durable attempts. Ragas is not another durable runner.

Checkpoint bounded sampling, extraction, synthesis, and evaluation units under the existing job/attempt identity. Check cancellation during preparation as well as before each gateway dispatch; a library executor handle returned after preparation cannot cancel earlier work by itself. Recheck the current attempt fence before persisting results, and do not hold a transaction open while waiting on a model.

Gateway-owned retries and budgets apply to nested calls and repairs too. Library retries must not multiply them. Budget exhaustion stops new dispatch with completed results retained, using existing failure outcomes. Cancellation cannot recall an already sent request; an unknown paid outcome follows [uncertain recovery](#uncertain), not silent resume/replay. A safe resume skips completed units; continuing after uncertain work requires the explicit recovery decision described below.

An authorized person may resume the same job only after checking its current project or resource scope, ownership, retained data, and remaining work. Keep its checkpoints and attempt history. Resuming cannot revive a generation marked for permanent deletion, replace its fixed payload, or repeat an uncertain paid call. Cancellation is checked between units of work and cannot undo an already completed call or release.

<a id="uncertain"></a>

## 2. Separate safe retries from uncertain work

A PostgreSQL lease controls database ownership. It does not control whether an external service continues executing a request.

### A lost model response is not permission to call the model again

Suppose the worker sends a model request and loses its connection. The provider may have completed and charged for the request, but Inframeld cannot determine that from the missing response.

Mark the operation `recovery_required`. **Do not automatically send another paid request**, even if a new attempt has taken over the database lease.

After reviewing the uncertainty, an operator may explicitly authorize a **new operation**. This is a new decision, not continuation of the old one.

Keep Inframeld's operation ID whether or not the provider returned its own reference. Save a provider reference only when one was actually returned.

### A captured vector payload has a different retry path

A vector generation contains embeddings the model has already produced. Before sending them to Chroma, [Indexing](indexing.md) saves their exact record IDs and payload, meaning all the values to be written.

If Chroma's response is lost, the worker can send **those same IDs and saved values** again, verify the stored records, and mark them ready only while it still owns the job. It does not call the embedding model again.

This is a safe repeat within the existing job. It creates neither a new public operation nor a new provider request, so it does not contradict the rule for uncertain model calls.

| Situation | Required handling |
| --- | --- |
| **Model response lost. Provider outcome unknown** | Record `recovery_required`. Do not automatically redispatch the chargeable call. |
| **Chroma insert response lost. Exact immutable IDs and payload retained** | Retry or verify through [Preparing and searching reliable indexes](indexing.md)’s bounded protocol, then publish only while the job still owns its fence. |
| **Retry payload missing/corrupt, stored records mismatched, or failure persistent** | Use the explicit recovery path rather than invent replacement data or continue ordinary retries. |

A delayed write of identical data does not change an immutable generation. It still matters during cleanup, because an old external write might finish after the application has begun deleting that generation.

**A lost response while inserting candidate data must not disable an otherwise healthy index.** The fence controls which attempt may publish readiness, not when Chroma finishes a request. This retry design still needs the [Indexing tests](indexing.md) before its behavior is verified.

<a id="requests"></a>

## 3. Identify the same request

Every state-changing command requires an opaque **`Idempotency-Key`**, at most **128 characters**. Queries that call a provider need it too, because repeating them can repeat paid work. GET requests do not require this header.

An HTTP command must receive exactly one `Idempotency-Key` header. Duplicate headers are invalid and must be rejected before reserving an operation.

[The accepted Access mutation profile](access-contracts.md#mutation-profile) limits new Access-management JSON bodies to 32 KiB and new bulk requests to 100 explicit assignments, with unknown fields rejected in new schemas. It preserves existing published models and does not cap document/configuration payloads. Access uses `expectedAccessRevision`; domain owners retain their own revisions. Find the original operation before considering a current revision as new work, then apply current authorization to recovery. Creation uses 201, completed metadata changes 200, and durable remaining cleanup 202 through the owning operation's result.

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

### Reserve the key alongside admission

Save the key reservation together with the accepted command. It records the request fingerprint, stable operation or job ID, state, expiry, and safe outcome.

A **canonical request fingerprint** is a consistent summary of the meaningful input. Equivalent requests produce the same fingerprint. Reusing a key with different input produces a conflict.

For uploads, use the validated file bytes and fields that affect meaning. Ignore multipart boundaries, which only format the HTTP upload and can differ between equivalent requests.

Hold uploads in private temporary storage with resource limits before accepting them. Delete an unaccepted upload only when its ownership is positively known. Looking unused is not enough.

### Fingerprint secret-bearing requests without exposing the secret

Requests containing secrets need a **keyed HMAC fingerprint**. This is a hash calculated with a separately protected deployment key. **Domain separation** labels its purpose so the same fingerprint cannot be confused with another use of HMAC.

Do not save raw request bodies or ordinary, unkeyed hashes of easily guessed secrets in retry records. An attacker could guess a weak secret and compare hashes. Use the selected keyed fingerprint instead.

Keep the fingerprint key stable for the whole retention period and include it in protected recovery of the installation.

Changing a submitted credential must produce a conflicting fingerprint even when every non-secret field remains identical.

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

### Trace one grant and its retries

Alice assigns Bob use-only `create-access-groups` permission with key `grant-bob-1` and expected project access revision `0`. The diagram abbreviates the key as K and the saved operation ID as O. The implemented grant command fingerprints the meaningful fields and checks current authority on every attempt. Its reservation, grant, new revision, and audit event commit together.

```mermaid
sequenceDiagram
    actor Alice
    participant HTTP as Grant HTTP route
    participant Service as Grant command service
    participant DB as PostgreSQL

    Alice->>HTTP: POST grant with key K and expected revision 0
    HTTP->>HTTP: Authenticate, validate one key, check CSRF, fingerprint input
    HTTP->>DB: Begin transaction
    HTTP->>Service: Assign use-only grant
    Service->>DB: Read current actor, recipient, and project facts
    Service->>Service: Check current Access policies
    alt Caller no longer allowed
        Service-->>HTTP: Deny or hide project
        HTTP->>DB: Roll back
        HTTP-->>Alice: 403 or 404, no replay
    else Caller allowed
        Service->>DB: Reserve principal, organization/project, method, route, K, and fingerprint
        Note over DB: Unique scope makes concurrent equal requests share one operation
        alt New key or expired completed reservation
            DB-->>Service: New operation O
            Service->>Service: Compare expected and current revision
            alt Revision stale
                Service-->>HTTP: Stale revision
                HTTP->>DB: Roll back new reservation
                HTTP-->>Alice: 409 stale_revision
            else Revision current
                Service->>DB: Save grant, revision, and audit
                Service->>DB: Mark O replayable and store expiry
                HTTP->>DB: Commit all changes
                HTTP-->>Alice: 201 with O and idempotencyExpiresAt
            end
        else Existing key with changed fingerprint
            DB-->>Service: Request meaning differs
            HTTP->>DB: Roll back
            HTTP-->>Alice: 409 idempotency_key_reused
        else Existing key with same fingerprint and safe result
            DB-->>Service: Original O and expiry
            HTTP->>DB: Commit without another grant change
            HTTP-->>Alice: 201 with original O and expiry
        end
    end
```

For example, if Carol is also an eligible project member, changing Bob to Carol while keeping `grant-bob-1` conflicts. Losing permission blocks a replay before the saved result is returned. Once completed history expires, the same key is treated as a new request. Alice's old expected revision would then fail the grant's revision check. Expiry limits duplicate detection, not the lifetime of Bob's grant.

The grant route exercises the safe-result path. The in-progress, asynchronous `202`, uncertain, issued-secret, and answer-receipt outcomes above retain their separate contracts. Their owning workflows still need implementation where noted.

## CLI Recovery Contract

The terminal and CI use the same saved backend operation. For a new command that changes state or can incur a charge, the CLI generates a request key unless automation supplies `--idempotency-key`.

A retry keeps the original target, account, project, command meaning and accepted inputs. If the acceptance response was lost, first look up the original operation. Changing the selected target or editing the Pipeline does not change what that retry means. Local recovery hints can help locate an operation, but cannot prove what the server did or grant permission to continue.

`Ctrl-C` requests cancellation. Pressing `c` stops watching and returns to the shell without canceling backend work. Report whether cancellation was merely requested or actually completed.

Human commands wait by default. The caller can explicitly choose to return after the backend accepts work, and a wait timeout does not cancel that work. Scripts must not encounter unexpected prompts. They receive separate command and job outcomes. Exact transport, output and signal contracts still need specification. A terminal mockup does not define them.

Configuration imports use these same durable jobs. They retain the approved definitions, destination mappings and completed resources. Continue only unfinished steps that the backend confirms are still safe and permitted. Changed inputs need a new review. An uncertain write must be resolved before it is repeated.

Query retries still return receipts rather than answer text, and one-time secrets retain their special recovery restrictions. If the backend's original history has expired, the CLI must not automatically create new paid work. [The delivery plan](cli-delivery-plan.md) assigns lookup, progress, continuation and qualification work. It does not replace the implemented grant-idempotency behavior.

<a id="identity-cleanup"></a>

### Reconcile the original identity-cleanup obligation

Verified recovery/reset admits one trusted flow-bound cleanup identity and temporary product block under the [Access contract](access-control.md#identity-recovery-cleanup). Suspension likewise commits its immediate local block, revision/audit and original durable cleanup obligation together. These workflows use ordinary durable jobs/reconciliation, not another queue or public state machine.

Record Kratos-session and Hydra-grant outcomes independently. Confirmed success, failure and uncertainty are different evidence. Keep provider waits outside SQL transactions and retries bounded. One provider succeeding never releases the block while another required outcome is unconfirmed. Reconcile the original admitted operation instead of restoring access to retry provider work.

A completed duplicate recovery event returns the original result. It must not start broad cleanup against credentials from a subsequent login. An older operation finishing cannot release a newer pending block. Otherwise active humans automatically resume only after all required cleanup is confirmed and current local eligibility holds; suspended humans still require separately authorized restoration/security review. No completion recreates removed assignments. The [private recovery handoff draft](access-contracts.md#recovery-wire) specifies stable original-flow/identity/kind/phase deduplication and durable acknowledgment. #117 still qualifies hook ordering, trusted completion and bounded reconciliation; these are specification requirements, not implemented cleanup evidence.

<a id="project-deletion"></a>

### Continue only the project deletion that was admitted

[Access admission](https://github.com/matejpalenik/inframeld/issues/204) checks current eligible human, membership, exact Delete project permission and reviewed state under the shared organization/project locks. It commits the project block, audit, original operation binding and exact durable cleanup obligation together. Denial or a stale review leaves no partial block. [Application lifecycle](https://github.com/matejpalenik/inframeld/issues/30) stops project applications and revokes their keys before [physical cleanup](https://github.com/matejpalenik/inframeld/issues/45). Failed or uncertain shutdown/cleanup keeps the block and original obligation; racing work cannot reopen the project.

Distinguish admitted/access-blocked, shutdown-unfinished, physical-cleanup-unfinished and cleanup-complete outcomes. These meanings do not choose a new job enum. After a lost acknowledgment, look up the original operation before retrying. Workers continue only its admitted exact project scope, without resurrecting the project, consulting a cached user-permission snapshot or affecting another project.

The currently eligible original initiating human may read retained content-free status after membership removal, based on the authoritative original principal/operation binding. Unrelated principals cannot claim that exception. Return no private inventory, hidden names, private-content counts or excerpts; status grants neither cancellation nor continuation. [Deletion-status delivery](https://github.com/matejpalenik/inframeld/issues/38) and [job contracts](https://github.com/matejpalenik/inframeld/issues/124) still own schemas, retention and protected lookup. This rule is accepted design, not an implemented status route.

<a id="automation-recovery"></a>

### A failed command is not permission to start again

CI submits work with request key `import-ci-42`, but the acknowledgment is lost. The backend may already have accepted the operation. Report that uncertainty. Do not invent a job ID, claim that no work started or automatically replace the key.

Look up the original request using its original target, principal, project and meaningful inputs. Only the retained backend record can establish the result. The [automation outcome contract](api-contracts.md#cli-automation-outcomes) explains command results, JSON and exit codes.

When a known job is read successfully, a failed job state can accompany a successful inspection command. Waiting for that job's failed requested workflow instead returns non-success, preserving confirmed partial effects. Neither reading nor watching reruns work. A previously returned admission acknowledgment does not establish current progress; a separate authorized read does. A wait timeout is not cancellation. A missing final output record is not proof that the server stopped.

If the original review and inputs remain applicable, only backend-confirmed eligible unfinished work may resume through the existing contract. Changed input or relevant state requires fresh reviewed work, not rewriting the original operation. Unknown paid outcomes remain unsafe to repeat even after the job's identity is recovered. Expired/restored/missing history limits duplicate-detection guarantees; do not promise guaranteed recovery or silently resubmit as new work. Local hints and saved credentials supply neither authoritative server history nor missing permissions.

Keep Ctrl-C's cancellation request, its acknowledgment and actual termination distinct. `c` detaches the view; it cannot cancel or close the user's terminal. Cancellation or an output failure cannot roll back completed effects. Bounded retry, receipt-only answers, show-once secrets and current-authority checks remain unchanged. #124/#156 specify concrete mappings and #175/#187 must prove the CLI behavior; this section is accepted design, not implementation evidence.

<a id="import-recovery"></a>

### An interrupted import keeps its original meaning

[The v1 provisioning boundary](access-contracts.md#provisioning) rejects application plans requiring new configurable resources before known-ineligible mutations. Eligible updates to existing resources retain the recovery rules below. Later permission/state changes can still leave confirmed partial effects; they never authorize replay as a human or creating missing dependencies.

Bob's import creates two resources and reuses three existing ones. Before its final step, the Pipeline changes, so the reviewed update can no longer be applied. Preserve the five confirmed outcomes and report the unapplied action. Do not undo the creates or replay completed updates.

Reusing a resource does not write it. Any remaining step that needs it must still check its current state and permissions. The [worked import example](configuration-portability.md#import-recovery) explains the resource workflow and terminal output.

Recovery first finds the original admission/job under its original context. An unchanged, retained review can support explicit continuation of eligible unfinished work through ordinary current checks. Changed definitions, mappings or relevant state instead require fresh review/admission; they cannot replace the old job's inputs. A new reviewed import may reuse completed resources after current comparison, while the old partial history remains intact. Exact relationship/projection contracts remain #151/#124 work, not a new generic workflow engine.

An uncertain child write is neither a confirmed success nor a confirmed failure. Reconcile its original command/result before repeating it. Replaying an earlier successful response must not restore old configuration over a later edit. Lost local connectivity does not prove failure, and missing authoritative history does not prove absence of effects. Report those limits without silently creating another import. Cancellation prevents only work the ordinary cancellation boundary can stop; it cannot undo committed resources or eliminate the need to reconcile a late write. No import recovery implicitly calls models, syncs documents, builds or publishes.

<a id="progress-presentation"></a>

### Show useful progress in plain language

Alice evaluates 20 cases. Seventeen finish before the project spending limit prevents the next call. Tell her: "Evaluation stopped: project spending limit reached. 17 of 20 cases completed. Their results are saved." Identify the three not-started cases through Evaluation's protected results and offer inspection. Offer `job resume` only when the backend reports eligible remaining work; admission still rechecks current authority, retained inputs and spending. Resolving the budget does not restart work automatically.

[CLI progress and result presentation](https://github.com/matejpalenik/inframeld/issues/175) selects concise outcome/reason/next-action copy without removing counts or results. The initiating domain supplies meaningful units and saved outcomes; shared job support supplies operation state and recovery eligibility. Do not add a universal per-item tracking framework or job states to fill a screen. [Evaluation](evaluation.md#result-presentation) owns questions, scoring and case details.

- Show actual progress when known, with a named unit and denominator. Do not invent a percentage, time estimate, zero or successful result when information is unavailable. Preparation can show its current activity without a case count.
- Separate an answer being saved from its scoring being complete. Partial, failed, canceled, unattempted and uncertain work must remain distinguishable. A total or saved-result statement must come from authoritative retained observations, not elapsed time or local guesses.
- Use a short default summary and a bounded list of items needing attention; link to ordinary inspection for the rest. Summaries, identifiers, questions and counts all remain subject to current access and erasure. Do not fetch every protected item merely to render progress.
- `c` stops watching without sending cancellation and returns to the shell; it does not close the user's terminal. Ctrl-C requests cancellation. Acknowledge locally that cancellation is being requested, but report "Cancellation requested" only after server acknowledgment and "Job canceled" only after confirmation. If acknowledgment is lost, report it as unconfirmed and offer status lookup.
- A lost CLI connection means the job **may** still be running, not that it certainly is. Look up the original operation before starting again. A model request with an unknown paid outcome instead requires review; say that it may have been charged and was not retried when those facts are established. Ordinary resume cannot repeat that call.
- Human and JSON views expose the same authorized facts and recovery limits. Human progress goes to stderr when stdout carries JSON; no animations or interactive key handling in noninteractive output. Reading or watching results does not rerun work.

These are accepted presentation requirements, not implemented guarantees or a wire schema. #124 owns precise backend outcomes, #156 the CLI output mapping, #175 presentation, and #39/#187 qualification. Preserve the existing lifecycle and bounded cancellation/recovery rules below.

<a id="secrets"></a>

## 4. Recover secret operations safely

Creating an Inframeld key and saving a customer's provider key have different recovery paths. The first creates a secret the user must receive. The second receives a secret the user already has.

### Inframeld-issued API and service keys are shown once

Generate incoming API and service keys from at least **32 cryptographically random bytes**. Store only their hash, safe prefix, permitted scope, owner, expiry and revocation state, and safe metadata.

Return plaintext once on successful creation. **Never store it in an idempotency response cache.**

For example, an administrator creates a CI credential using idempotency key `create-ci-7`. Inframeld creates credential K, but the connection drops before the administrator receives K’s plaintext.

Retrying `create-ci-7` returns K’s identifier and **`secretAvailable: false`**. It neither creates another credential nor recovers the original secret.

The administrator revokes K, then requests a new key with a new idempotency key. The retry deliberately returns a safe description of the first creation, not a copy of its secret-bearing response. [The application-key lifecycle](access-contracts.md#key-lifecycle) records `secretAvailable: true` only for first delivery; incoming keys remain bound to the server-derived installation/project and current account, not a caller-submitted permission set.

Invitation issuance likewise generates a 32-random-byte protected token, stores only verification material and safe metadata, and delivers plaintext once. The [HTTP draft](access-contracts.md#http-operation-matrix) specifies first-delivery/replay fields and the separate activation reservation bound to verified Kratos authority/subject before local admission; original activation resolves consumption before any new-write checks. Lost-response recovery cannot mint a second invitation or recover cached plaintext. [Invitation activation](access-contracts.md#invitations) instead recovers the original consumed intent and assignments under its verified-recipient admission boundary.

### Submitted provider credentials are never echoed

A provider-credential submission never returns the submitted secret, so its safe status can be replayed.

The [PostgreSQL credential adapter](model-connections.md) saves the encrypted secret, its credential revision, and the safe retry outcome in one transaction. **Ciphertext** is the encrypted value. Keeping these together avoids a separate vault write that could succeed while the database write fails, or vice versa.

The request uses the same keyed fingerprint described above. The API never returns the saved provider key.

<a id="answers"></a>

## 5. Recover an answer through its receipt

An **answer receipt** is a saved, size-limited record of which version answered a query and how it finished. It does not store the full response body.

| Receipt information | Purpose |
| --- | --- |
| **Selected pipeline version, deployment revision, rollout, and actual cohort** | Identify the configuration and routing selection actually used, not whichever version is current later. A cohort is the request’s rollout group. |
| **Originating stable principal** | Identify the human or application that requested the answer. |
| **Citations and every document/version used in final generation context** | Support current access checks, including for sources the model used but did not cite. |
| **Safe outcome and timing** | Report the recorded result of the operation without storing the full answer or snippets. |

Reserve the answer ID when accepting the query. Complete the safe receipt **before returning the finished response**.

Source IDs let the backend check current document access later, even if a feedback comment quotes a source the answer did not cite. These IDs do not store the source text itself.

### First responses and completed retries are deliberately different

| Request outcome | Returned content |
| --- | --- |
| **First successful query response** | The answer, `answerId`, and operation identity. |
| **Completed retry with the same key** | The receipt/status with **`responseAvailable: false`**. No new model call and no claimed replay of the original answer. |
| **Deliberately new query with a new key** | A new requested operation, which may incur another provider call. |

A client that needs the full answer must retain its successful response.

Suppose question Q was sent, but the caller lost the response. Repeating the same key reports work still running, the known receipt, or an uncertain outcome. It does not silently call the model again to reconstruct Q’s answer.

A short-lived full-response replay cache could be considered later through a separate retention decision. It is not implied by idempotency and is not part of this design.

### Make the difference visible to clients and feedback

OpenAPI must describe the first answer and receipt-only retry as different response variants. SDKs must report which one arrived, rather than display a receipt as an empty answer.

[Answer feedback](answer-feedback.md) refers to this receipt instead of creating another response log. Receiving only a receipt must not generate feedback about an answer the caller never received.

<a id="revisions"></a>

## 6. Protect competing edits and retained history

Idempotency prevents duplicate execution of one requested action. It does not resolve two different actions that compete to change the same state.

Alice and Bob both try to promote Deployment revision **12**, using different idempotency keys. These are two competing decisions:

| Command | Result |
| --- | --- |
| **First conditional update against revision 12** | Succeeds and advances the Deployment to revision **13**. |
| **Second conditional update against revision 12** | Updates zero rows because revision 12 is no longer current. Returns **`409 stale_revision`**. |

Each protection answers a different question: the idempotency key identifies a repeated request, the revision detects another person's intervening change, and the fence proves which worker attempt may save the result.

### Limit guarantees to retained, authoritative history

Keep completed duplicate-detection records for **at least 24 hours** and for as long as their work remains active. Publish their expiry time. After expiry, the server no longer promises to recognize that old request.

The implemented project-grant response publishes the stored deadline as `idempotencyExpiresAt`. An authorized replay returns that same timestamp; retrying does not extend the retention window. The deadline limits duplicate detection; it does not delete the grant.

A new idempotency key always identifies a new requested operation, even when its input equals a previous request. Clients must not generate new keys merely because the original response was lost.

### Disaster restore requires reconciliation before replay

A backup contains records only up to its capture time. Restoration can therefore lose later accepted work and completion records. The declared **recovery-point window** describes how much recent history may be missing.

For example, a job may be `queued` in the backup and have made a paid provider call before the failure. Restoring that backup makes the old queued state visible again. **It does not prove that the later call never happened.**

Before restarting provider-capable jobs or replaying builds, evaluations, or releases, follow [recovery reconciliation](upgrades-and-recovery.md). This means using the evidence that remains to decide what can safely run despite the missing history.

Do not promise deduplication or exactly-once external effects for history absent from the restored backup.

<a id="connection-changes"></a>

### Preserve operation identity across shared connection changes

Admitted work records selected connection IDs and the current access revisions it observed, separately from fixed Pipeline/model/corpus inputs. Before each model dispatch, resolve current access and apply [the gateway freshness rule](model-connections.md#dispatch-freshness). A relevant access change stops remaining model work; it is not permission to use the old revision, rebind the existing job or retry against new settings automatically. Credential-only rotation and metadata rename remain independent.

A known revision/precondition failure uses the existing failed outcome with a safe explanation. An uncertain dispatched paid call retains recovery-required handling. Keep completed checkpoints with actual revision attribution. Changed settings require new explicit admission and cost review; resuming the same job must not relabel old units or adopt a newer access revision. Previously captured immutable vector payloads retain their ordinary bounded storage-retry path, but this permits neither new model calls nor automatic publication under changed consent.

Connection updates themselves are conditional, idempotent commands. Recheck reviewed revisions, current management authority, complete dependency impact and embedding compatibility in coordination with new bindings/preparation admission. Commit configuration, required credential transition, audit and safe replay outcome together. No external model call occurs inside that transaction. Lost responses recover the original metadata-only outcome; replay after another update does not restore the earlier state. Exact public schemas and concurrency mechanisms remain implementation work, not another workflow framework.

<a id="capture-experimental-inputs-before-preparation-and-preserve-them-on-retry"></a>

### Capture working-configuration inputs before preparation and preserve them on retry

Alice admits an evaluation of working revision 18, then saves revision 19 while its preparation is running. The existing job retains revision 18, its explicit overrides, exact corpus and eventual fixed verified bindings. Direct-query/evaluation preparation uses ordinary bounded jobs and checkpoints, without creating a release version. No child completion acquires publication authority.

On a repeated request, find the original operation before resolving the current working revision, collection selection or sole Deployment again. The same key cannot capture revision 19 or a newly created target and charge for a second operation. An explicit new request is required for changed inputs. Admission checks expected reviewed revisions; conflicts are not automatically retried with fresher consent.

The user-facing policy-controlled Build likewise captures the saved configuration and target exactly once. Its ordinary build child records readiness; only a separately authorized publication child may change traffic. Record ready-but-unpublished distinctly from preparation failure, and preserve a successful build when permission, mode, candidate state or a newer request prevents publication.

Cancellation covers preparation, between evaluation cases and before gateway dispatch. A canceled/superseded workflow cannot later publish merely because a child finishes. Already dispatched model calls may finish and charge; uncertain outcomes retain `recovery_required`, not an automatic paid retry. CLI Ctrl-C requests cancellation, while `c` only detaches a durable progress view. Reopening a watcher observes the same job without resubmission. Canceling after publication committed cannot undo the release. [Pipelines](pipelines-and-releases.md#preview) and [CLI development loop](https://github.com/matejpalenik/inframeld/issues/172) own user-visible context and outcomes.

<a id="automatic"></a>

## 7. Reuse these rules for automatic publication

Automatic updates use these same jobs and keep stable IDs for their child operations. The underlying preparation and publication are separate application commands, even when the CLI Build workflow admits both together. Only one update runs per Deployment at a time. A newer authorized live-input update or automatic Build removes an older one's permission to publish, without changing the older build's fixed inputs. A working edit, restore, direct Pipeline queries or evaluation does not supersede publication work.

The [publication-mode guide](pipelines-and-releases.md#modes) defines the full checks. A worker cannot substitute a newer revision to make an outdated request valid. After a crash, it finds the recorded release change instead of publishing twice. Canceling pending work does not reverse a release already saved.

### Deduplicate default-route requests before resolving a new target

The **recommended project-default serving alias** is a stable logical route that can point to an actual Deployment. Its target can change over time.

For a default-route request, first look for the original request using that logical route, project, and principal. Only a genuinely new request resolves the current Deployment. Save the first accepted target choice.

For example, the default route points to Production when SupportBot asks a question, then is changed to Test. Retrying the same key finds Production's original receipt or outcome and checks current access to it. It must not pay for a new query against Test. A promotion inside Production also leaves retries attached to their original operation.

HTTP and MCP apply this same rule for identifying a route. Explicitly requesting a different route gives the request a different scope.

<a id="maintainer-checks"></a>

## 8. Maintainer checks

The following acceptance cases verify the behavior above. They are implementation requirements, not completed qualification.

| Area | Required verification |
| --- | --- |
| **Duplicate admission** | Simultaneous equivalent requests with the same key create one job. Different payloads conflict, including changed submitted credentials. |
| **Replay authorization** | Current permissions are rechecked. A remembered key does not bypass revocation or lost document access. |
| **Credential responses** | Plaintext secrets never enter logs or SQL response caches. A lost issued-key response follows the documented revoke-and-reissue path without creating a duplicate credential. |
| **Query retries** | Retrying does not repeat a model call. First-answer, receipt-only, in-progress, and uncertain outcomes remain distinguishable. |
| **Worker ownership** | Stale fences cannot record authoritative progress or publish results. |
| **External uncertainty** | Crashes between external dispatch and result persistence use the correct recovery path: exact captured vector writes differ from ambiguous model calls. |
| **Retry lifecycle** | Bounded attempts, exhausted-budget failure, safe authorized resume, preserved checkpoints/history, and cancellation follow the recorded rules. |
| **Competing release changes** | Independent commands cannot both update the same expected Deployment revision. |
| **Automatic updates and aliases** | Superseded work cannot publish, lost publication acknowledgements do not repeat transitions, and alias changes do not turn retries into new queries. |
| **Restore** | Restored queue state does not automatically authorize replay when later provider activity may be missing from the backup. |

<a id="decision-map"></a>

## 9. Decision and reference map

External work is not guaranteed to happen exactly once. [Recovery](upgrades-and-recovery.md) handles missing backup history, and [Indexing](indexing.md#retries) defines the specific safe retry for saved vector payloads. Queue limits, safe resume, cancellation, and cases needing human intervention must remain explicit. A `failed` label alone cannot tell us whether repeating work is safe.

| Decision | Rationale |
| --- | --- |
| [ADR-0026](../adr/ADR-0026-persist-background-work-through-controlled-durable-attempts.md) | Persist background work through controlled durable attempts. |
| [ADR-0027](../adr/ADR-0027-identify-repeated-requests-by-caller-and-request-meaning.md) | Identify repeated requests by caller and request meaning. |
| [ADR-0028](../adr/ADR-0028-recover-answer-requests-through-receipts-without-a-full-answer-replay-cache.md) | Recover answer requests through receipts without a full-answer replay cache. |
| [ADR-0029](../adr/ADR-0029-use-expected-revisions-to-protect-competing-changes.md) | Use expected revisions to protect competing changes. |
