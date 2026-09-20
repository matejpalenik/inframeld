# ADR-0007: PostgreSQL jobs, idempotency, and honest retry semantics

**Status:** Accepted — jobs and idempotency design; implementation qualification pending. **Revised:** 19 September 2026. **Required approach:** PostgreSQL-backed durable jobs, request deduplication, and explicit handling of uncertain external outcomes in the supported production Docker Compose deployment. **Related:** [Vector writes](ADR-0004-postgresql-source-of-truth-and-shared-chroma.md), [release transitions](ADR-0009-sticky-logical-canary-deployments.md), [recovery](ADR-0013-minimal-hosted-observability-and-recovery.md).

## Context

Inframeld performs work that can outlive an HTTP request: processing documents, building indexes, running evaluations, and changing releases. It also makes model calls that may incur a charge and creates credentials whose plaintext must not be retained for later retrieval.

From first principles, **not receiving a response does not prove that the operation failed**. A worker can stop after completing part of a build. A provider can process a model request even though its response never reaches Inframeld. An administrator can lose the response containing a newly created API key.

These situations require different answers. We need to remember accepted work, distinguish a duplicate request from a new one, and retry only when doing so is demonstrably safe. We must also explain when an outcome is unknown or a response cannot be recovered, rather than hide another model call or retain secrets merely to replay them.

Three mechanisms address different problems:

| Mechanism | Question it answers |
| --- | --- |
| **Idempotency key** | Is this a retry of the same requested operation? |
| **Job fence** | Does this worker attempt still have authority to record progress or publish a result in PostgreSQL? |
| **Expected revision** | Is this change based on the same application state the caller originally observed? |

None of these, by itself, cancels an external request or proves that a remote side effect happened exactly once.

## Decision

**Use PostgreSQL to record durable jobs and deduplicate requests. Retry only work with a proven safe replay path. Preserve uncertain outcomes explicitly, and return documented safe results without caching plaintext secrets or full production answers.**

A **durable job** is a stored record of background work, including its identity and progress. An **operation** identifies the accepted application request; its background execution can be tracked by a job. An **attempt** is a recorded try at executing work. Retrying an attempt does not create a new requested operation.

### 1. Admit work and claim jobs through short PostgreSQL transactions

**Admission** means durably accepting an operation. The API records the job, its request-idempotency reservation, known business identities, and required audit evidence in one transaction. They commit together rather than leaving accepted work without a matching job or duplicate-detection record.

Not every identity must be known before the job starts. A discovery job can call ordinary application commands to admit newly discovered documents or generations before performing their associated side effects. Starting a synchronization does not require the HTTP request to pre-discover a million S3 objects.

#### One worker owns the supported queue

One worker polls PostgreSQL for eligible jobs. For each claim, it:

1. **Claims the work in a short transaction.** Lock and claim a bounded job, recording the attempt, owner, expiry, and fence, then commit.
2. **Performs the work outside that transaction.** Do not hold the SQL transaction open while processing files or waiting for an external service.
3. **Records progress and completion conditionally.** Progress and final publication must present the same current fence.

A **lease** is the time-limited claim on the job. A **fence** is the token identifying the currently authorized attempt. PostgreSQL accepts its progress and publication writes only while that token still matches the current ownership record.

If an attempt loses ownership, it becomes **stale**. It cannot publish authoritative PostgreSQL state, even if it later finishes its work.

#### Keep queue infrastructure proportionate to one server

PostgreSQL supplies the queue for the supported single-server deployment. Index the job status and next-attempt values used to find eligible work, bound concurrency and queue capacity, and monitor the age of the oldest queued work.

SQS, Kafka, Redis, dead-letter queues (DLQs), a delivery outbox, and a workflow engine are not v1 dependencies. A delivery outbox would record notifications awaiting delivery; webhook delivery is deferred. A future notification workflow may justify one, but the existence of a `WebhookDispatcher` interface does not require unused delivery infrastructure now.

### 2. Preserve progress and distinguish failure from uncertainty

The job lifecycle uses these states:

```text
queued -> running -> succeeded | failed | canceled | recovery_required
```

**Checkpoints** identify completed files, batches, or evaluation cases. They let later safe attempts preserve completed work rather than restart everything.

Automatically retry only clearly safe work: work known not to have been dispatched, or work whose repeated execution is idempotent. Use bounded **backoff**, meaning a controlled wait between attempts, and **at most three application attempts**.

If the retry budget is exhausted, record `failed` with a typed exhausted-budget reason. A typed reason is a defined error category that clients can distinguish. There is no separate `paused` state.

**`failed` and `recovery_required` are not interchangeable.** A failed operation may have exhausted its safe retries. An uncertain external outcome without a proven replay path instead requires a recovery decision; another automatic attempt could repeat work that already happened.

#### Resume the same job only when the remaining work is safe

An explicit, authorized resume may requeue the same job after checking current scope, ownership, retention, and a proven safe replay path for its remaining work. Preserve its completed checkpoints and attempt history.

Resume must not revive a **tombstoned generation**, whose physical identity has been permanently retired. It must not change a frozen payload or implicitly authorize another model call whose earlier outcome is unknown.

#### Cancellation is a request to stop, not a reversal

Cancellation records intent, which the worker checks between bounded units of work. It cannot undo a completed model request or a release that has already been published.

### 3. Treat uncertain model calls differently from immutable vector writes

A PostgreSQL lease controls database ownership. It does not control whether an external service continues executing a request.

#### A lost model response is not permission to call the model again

Suppose the worker sends a model request and loses its connection. The provider may have completed and charged for the request, but Inframeld cannot determine that from the missing response.

Record `recovery_required`. **Do not silently send another chargeable request**, including after reclaiming the SQL lease.

An operator may explicitly authorize a **new operation** after seeing the uncertainty. That is a new decision, not an automatic continuation disguised as a retry.

Always retain an application operation reference. Record a provider reference only if the provider actually returned one; its absence does not remove Inframeld’s own operation identity.

#### A captured vector payload has a different retry path

A vector generation contains numerical embeddings already produced by the model. Under [ADR-0004](ADR-0004-postgresql-source-of-truth-and-shared-chroma.md), its physical record IDs and exact write payload are captured durably before dispatch to Chroma.

If that insertion’s outcome is unknown, the worker can retry **the same IDs and the same saved payload**, verify the records, and conditionally publish readiness. This does not repeat the embedding-model call.

The retry stays inside the original job. It is neither a new public mutation nor a new provider request. The general rule against replaying uncertain external work does not prohibit this specifically safe protocol.

| Situation | Required handling |
| --- | --- |
| **Model response lost; provider outcome unknown** | Record `recovery_required`; do not automatically redispatch the chargeable call. |
| **Chroma insert response lost; exact immutable IDs and payload retained** | Retry or verify through ADR-0004’s bounded protocol, then publish only while the job still owns its fence. |
| **Retry payload missing/corrupt, stored records mismatched, or failure persistent** | Use the explicit recovery path rather than invent replacement data or continue ordinary retries. |

A delayed identical insert does not corrupt a live immutable generation. However, unresolved attempts still matter to final physical cleanup: an old external request may remain active after the application has moved on.

**A lost candidate-insert response must not make an entire healthy index unavailable.** The PostgreSQL fence protects publication, not external execution. The immutable-generation retry design is accepted for qualification; its implementation must still pass the tests in ADR-0004.

### 4. Identify duplicate requests by stable caller and request meaning

All state-changing commands require an opaque **`Idempotency-Key`**, with a maximum length of **128 characters**. This includes queries that invoke a provider: although called queries, they execute work that must not be repeated accidentally. GET requests do not require the header.

An opaque key is a caller-supplied identifier for the requested operation, not a source of permissions or business meaning.

Scope its reservation by:

```text
stable authenticated human/application principal
    + organization/project
    + HTTP method and route
    + Idempotency-Key
```

A **principal** is the stable identity Inframeld recognizes as the human or application caller. Credential IDs remain audit evidence, but they do not define a new duplicate-detection scope. Rotating a credential for the same principal must not silently make an old request look new.

**Authenticate and authorize again before replay.** A revoked credential or lost document permission cannot retrieve an old result merely because the caller remembers its idempotency key.

#### Reserve the key alongside admission

In the same transaction that admits the command, reserve the key and record the canonical request fingerprint, stable operation/job identity, state, expiration, and safe outcome.

A **canonical request fingerprint** represents the meaningful request content consistently. Equivalent requests match; changed requests conflict.

For uploads, fingerprint the validated streamed bytes and semantic fields, not multipart boundary formatting. Multipart boundaries are transport formatting and can change between equivalent uploads.

Stage uploads privately with bounded resource use before admission. Clean up unadmitted staging only when its ownership is positively known; do not delete objects merely because they appear unused.

#### Fingerprint secret-bearing requests without exposing the secret

Requests containing secrets use a **domain-separated keyed HMAC fingerprint** with a separately protected deployment key. HMAC is a keyed authentication hash; domain separation distinguishes this fingerprint’s purpose from other uses.

Never retain raw request bodies or an unkeyed digest of a low-entropy secret in idempotency metadata. A low-entropy secret is one that may be easy to guess; storing its ordinary hash is not an acceptable substitute for the selected keyed fingerprint.

Keep the fingerprint key stable throughout the retention window and include it in protected deployment recovery.

Changing a submitted credential must produce a conflicting fingerprint even when every non-secret field remains identical.

### 5. Return the documented outcome instead of starting duplicate work

After checking current authentication and authorization, apply the following response contract:

| Retry condition | Response |
| --- | --- |
| **Same key and equivalent request; safe result complete** | Replay the documented safe outcome without another mutation. An accepted asynchronous command follows the dedicated `202` rule below. |
| **Same key, different request** | `409 idempotency_key_reused`. |
| **Same key for an unfinished synchronous command or query** | `409 idempotency_in_progress`, the operation identity, and a useful `Retry-After` header. |
| **External outcome uncertain, with no proven safe replay** | The operation’s stable `recovery_required` status; no automatic redispatch. |
| **Same accepted asynchronous command** | The same `202 Accepted`, job identity, and `Location` header. |

A **synchronous** operation returns its result through the request being executed. An **asynchronous** command accepts background work and returns a job to follow. `Location` identifies that job resource; `Retry-After` tells the client when to retry checking.

**An accepted asynchronous command always replays its original `202` admission**, whether its job is running, complete, failed, or uncertain. It does not become a synchronous `409 idempotency_in_progress` response just because the job is still running.

The job resource separately reports its current state and retry progress. An internal immutable-vector retry remains part of that same job.

Client retry libraries must preserve the original key and respect `Retry-After`. Centrally configured model-gateway policy prevents nested SDK retries, where a software development kit silently repeats a provider call beneath the application’s own retry policy.

### 6. Handle credential responses without retaining plaintext for replay

There are two different operations: **issuing an Inframeld credential** and **receiving a customer’s provider credential**. Their safe replay responses differ.

#### Inframeld-issued API and service keys are shown once

Generate issued keys from at least **32 cryptographically random bytes**. Persist only the cryptographic hash, safe prefix, scope, ownership, expiry/revocation state, and metadata.

Return plaintext once on successful creation. **Never store it in an idempotency response cache.**

For example, an administrator creates a CI credential using idempotency key `create-ci-7`. Inframeld creates credential K, but the connection drops before the administrator receives K’s plaintext.

Retrying `create-ci-7` returns K’s identifier and **`secretAvailable: false`**. It neither creates another credential nor recovers the original secret.

The administrator revokes K and submits a new creation operation with a new idempotency key. This route deliberately has a sanitized retry representation rather than byte-for-byte replay of its first response.

#### Submitted provider credentials are never echoed

A provider-credential submission never returns the submitted secret, so its safe status can be replayed.

The encrypted PostgreSQL adapter selected in ADR-0020 commits **ciphertext, credential revision, and the sanitized idempotency outcome together**. Ciphertext is the encrypted representation of the secret. Using one PostgreSQL transaction avoids a separate vault write that would have to be coordinated with a database write.

The request uses the same keyed fingerprint described above. The API never returns the saved provider key.

### 7. Replay an answer receipt, not a hidden copy of the answer

A production query has a durable **answer receipt**: a bounded record of what served the request and how it finished. It is not a saved response body.

| Receipt information | Purpose |
| --- | --- |
| **Selected pipeline version, deployment revision, rollout, and actual cohort** | Identify the configuration and routing selection actually used, not whichever version is current later. A cohort is the request’s rollout group. |
| **Originating stable principal** | Identify the human or application that requested the answer. |
| **Citations and every document/version used in final generation context** | Support current access checks, including for sources the model used but did not cite. |
| **Safe outcome and timing** | Report the recorded result of the operation without storing the full answer or snippets. |

Reserve the answer identity at admission. Finalize its safe outcome **before releasing the completed response**.

The recorded source identities are not a stored context body. They support current authorization even when later feedback comments quote an uncited source.

#### First responses and completed retries are deliberately different

| Request outcome | Returned content |
| --- | --- |
| **First successful query response** | The answer, `answerId`, and operation identity. |
| **Completed retry with the same key** | The receipt/status with **`responseAvailable: false`**. No new model call and no claimed replay of the original answer. |
| **Deliberately new query with a new key** | A new requested operation, which may incur another provider call. |

A client that needs the full answer must retain its successful response.

Suppose question Q was sent, but the caller lost the response. Repeating the same key reports work still running, the known receipt, or an uncertain outcome. It does not silently call the model again to reconstruct Q’s answer.

A short-lived full-response replay cache could be considered later through a separate retention decision. It is not implied by idempotency and is not part of this design.

#### Make the difference visible to clients and feedback

The OpenAPI contract describes first-response and replay-response variants explicitly. SDKs must surface the replay outcome rather than treat it as an empty generated answer.

Answer feedback extends this same receipt rather than creating another response log. [ADR-0017](ADR-0017-answer-feedback.md) defines the accepted editable feedback contract. Receipt-only replay must not manufacture feedback about an answer the caller did not receive.

### 8. Use revision checks for competing changes

Idempotency prevents duplicate execution of one requested action. It does not resolve two different actions that compete to change the same state.

Suppose two requests both try to promote Deployment revision **12**. They use different idempotency keys, so they are genuinely separate commands.

| Command | Result |
| --- | --- |
| **First conditional update against revision 12** | Succeeds and advances the Deployment to revision **13**. |
| **Second conditional update against revision 12** | Updates zero rows because revision 12 is no longer current; returns **`409 stale_revision`**. |

Both mechanisms are required: **idempotency handles duplicate requests; revision checking handles competing requests**. A job fence handles the separate question of whether the worker attempt still owns publication.

### 9. Limit guarantees to retained, authoritative history

Retain completed deduplication records for **at least 24 hours** and throughout associated active work. Document the expiration timestamp. After expiry, the server no longer promises deduplication for that record.

A new idempotency key always identifies a new requested operation, even when its input equals a previous request. Clients must not generate new keys merely because the original response was lost.

#### Disaster restore requires reconciliation before replay

A backup captures state at a particular point. Restoring it can lose admissions and completion records written afterward, within the deployment’s declared **recovery-point window**: the period of history that recovery may not preserve.

For example, a job may be `queued` in the backup and have made a paid provider call before the failure. Restoring that backup makes the old queued state visible again. **It does not prove that the later call never happened.**

[ADR-0013](ADR-0013-minimal-hosted-observability-and-recovery.md) requires explicit reconciliation before resuming restored provider-capable jobs or replaying build, evaluation, or release work. Reconciliation establishes what can safely proceed given the retained evidence and any missing history.

Do not promise deduplication or exactly-once external effects for history absent from the restored backup.

### 10. Use the same durable operations for Automatic updates

**Automatic updates** in [ADR-0019](ADR-0019-default-onboarding-and-first-publication.md) uses ordinary durable jobs and child operation identities. A child operation identifies one constituent action, such as the build or release requested by the update.

Allow **one active automatic operation per Deployment**, processing frozen inputs. A newer authorized request supersedes the older operation’s eligibility to publish; it does not rewrite that operation’s inputs.

The update operation invokes **Build** and **Releases** separately. Build completion does not, by itself, grant authority to change customer traffic.

#### Publication must still match the latest authorized request

Switching modes advances a **control revision**, which identifies the publication-control state captured by an operation. Turning Automatic updates off and then on admits fresh work. It must not update an old job’s captured revision to make that job eligible again.

Final publication atomically checks:

| Check | What must still hold |
| --- | --- |
| **Captured control revision** | The operation still matches the current publication-control state. |
| **Newest request identity** | A newer authorized request has not superseded its publication eligibility. |
| **Job fence** | This execution attempt still owns publication. |
| **Expected serving state** | The Deployment still has the serving state the transition expects. |
| **Readiness** | The target version and its required resources are ready. |
| **Current authorization** | The action remains permitted now. |

Retries preserve their original update and child identities. If publication committed but its acknowledgement was lost, the recorded publication recovers that result without changing pointers twice.

Canceling, deleting, or rebinding a target invalidates pending publication. It does not undo a release already committed.

Superseded jobs may leave reusable artifacts, but they never silently adopt newer inputs. Safe Chroma retries and uncertain paid-provider outcomes retain their distinct handling in either publication mode.

### 11. Deduplicate default-route requests before resolving a new target

The **recommended project-default serving alias** is a stable logical route that can point to an actual Deployment. Its target can change over time.

For this alias, deduplicate using the stable requested logical route, project, and principal **before resolving a new actual Deployment**. Persist the first admitted target selection.

For example, a request through the default route is admitted to Deployment A. The alias is later rebound to Deployment B. Retrying the original key must replay A’s original, currently authorized receipt/outcome; it must not become a new paid query against B. Promotion within a Deployment follows the same principle: a retry stays with its recorded operation.

The API and **MCP**, the Model Context Protocol interface, share this route normalization. A different explicitly requested target route has its own request scope.

### 12. Test crashes and lost responses, not only clean retries

The following acceptance cases verify the behavior above. They are implementation requirements, not completed qualification.

| Area | Required verification |
| --- | --- |
| **Duplicate admission** | Simultaneous equivalent requests with the same key create one job. Different payloads conflict, including changed submitted credentials. |
| **Replay authorization** | Current permissions are rechecked; a remembered key does not bypass revocation or lost document access. |
| **Credential responses** | Plaintext secrets never enter logs or SQL response caches. A lost issued-key response follows the documented revoke-and-reissue path without creating a duplicate credential. |
| **Query retries** | Retrying does not repeat a model call. First-answer, receipt-only, in-progress, and uncertain outcomes remain distinguishable. |
| **Worker ownership** | Stale fences cannot record authoritative progress or publish results. |
| **External uncertainty** | Crashes between external dispatch and result persistence use the correct recovery path: exact captured vector writes differ from ambiguous model calls. |
| **Retry lifecycle** | Bounded attempts, exhausted-budget failure, safe authorized resume, preserved checkpoints/history, and cancellation follow the recorded rules. |
| **Competing release changes** | Independent commands cannot both update the same expected Deployment revision. |
| **Automatic updates and aliases** | Superseded work cannot publish, lost publication acknowledgements do not repeat transitions, and alias changes do not turn retries into new queries. |
| **Restore** | Restored queue state does not automatically authorize replay when later provider activity may be missing from the backup. |

## Consequences

### Positive

- **Accepted work and progress survive interrupted execution.** Stable job identities, checkpoints, and fences let the application track work without accepting a stale worker’s publication.
- **Retries do not silently become new operations.** Duplicate admission is prevented while authoritative history is retained. Exact vector writes have a safe retry path, while uncertain chargeable calls remain explicit recovery decisions.
- **Retry support does not require storing sensitive response bodies.** Sanitized credential results and answer receipts preserve useful status and provenance without a plaintext secret cache or hidden production-answer log. Current access still applies to replay.

### Negative

- **Some lost responses cannot be recovered in full.** A lost issued secret requires revocation and a new creation operation. A lost answer can yield only its receipt; obtaining another answer requires a deliberately new query that may incur a charge.
- **Not every failure is automatically recoverable.** Ambiguous model calls, unsafe remaining work, and damaged retry payloads can require an explicit recovery decision. Cancellation cannot reverse completed external work.
- **The guarantees require retained state and operational discipline.** Queue limits, checkpoints, fences, request fingerprints, protected key material, expiration, and restore reconciliation must be maintained. Expired or missing history cannot support an unlimited deduplication promise.

## Alternatives considered

The source records approaches that are unnecessary, excluded, or deferred under this decision. It does not record a separate comparative assessment.

### Add a queue broker, dead-letter queue, or workflow engine

**Not required for v1.** PostgreSQL is sufficient for the supported single-server queue when eligible work is indexed, concurrency/capacity are bounded, and queue age is monitored.

SQS, Kafka, Redis, DLQs, and workflow infrastructure are not introduced merely to execute these jobs. Webhooks and their delivery outbox remain deferred; an interface alone is not a reason to deploy a delivery system.

### Treat a reclaimed lease as proof of exactly-once external execution

**Ruled out.** A new database owner cannot cancel a request the old attempt already sent to a provider or Chroma. Fences protect PostgreSQL publication, not external execution.

Unknown model outcomes remain visible. Immutable vector writes use their separately defined exact-payload protocol.

### Automatically retry every timeout

**Ruled out.** A missing response can follow a completed, chargeable request. Automatic retries are limited to work known to be safe, with bounded attempts and central control over nested SDK retries.

An operator may explicitly authorize a new operation after seeing uncertainty, but ordinary resume does not grant that authority implicitly.

### Cache every response for byte-for-byte replay

**Not selected.** Issued credential plaintext is shown once and never cached. Submitted provider credentials are never echoed. Completed production-query retries return receipts rather than stored answers or regenerated replacements.

A short full-answer replay window may be considered later under a separate retention decision. It is not a requirement of idempotency.

### Use idempotency instead of expected revisions

**Insufficient.** Different idempotency keys identify separate valid requests. They can still compete against the same Deployment revision. Conditional revision updates are required alongside duplicate detection.

## References

| Reference | Responsibility |
| --- | --- |
| [ADR-0004: Vector writes](ADR-0004-postgresql-source-of-truth-and-shared-chroma.md) | Immutable vector generations, exact-payload retries, verification, and unresolved-write cleanup. |
| [ADR-0009: Release transitions](ADR-0009-sticky-logical-canary-deployments.md) | Deployment transitions and competing release changes. |
| [ADR-0013: Recovery](ADR-0013-minimal-hosted-observability-and-recovery.md) | Backup/restore limits and reconciliation before resuming restored work. |
| [ADR-0017: Answer feedback](ADR-0017-answer-feedback.md) | Editable feedback attached to the existing answer receipt. |
| [ADR-0019: Default onboarding and publication](ADR-0019-default-onboarding-and-first-publication.md) | Automatic updates, publication control, and the recommended project-default serving alias. |
| ADR-0020 | Persistent encrypted provider credentials and atomic storage with sanitized idempotency outcomes. |
