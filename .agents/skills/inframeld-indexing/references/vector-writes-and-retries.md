# Vector writes and frozen-payload retries

<a id="vector-writes-and-frozen-payload-retries"></a>

One shard accepts Alice's new vectors while another times out. The materialization is still unready. Recovery must establish which exact records exist without inventing another numerical execution or repeating a paid model call whose outcome is unknown.

<a id="capture-before-dispatch"></a>

## Apply accepted PD-INDEXING-04

Accepted [PD-INDEXING-04](decision-storage-retries-and-erasure.md#approved-resolution) selects this workflow's detailed contract. A timed-out storage request may still finish later. Reusing already known bytes is different from buying another embedding, and deleting data is not complete while old writes could recreate it. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## Capture before dispatch

The singleton vector writer stays in the existing worker and holds a process-lifetime local lock. API handlers never mutate Chroma.

SQL attempt/revision checks decide whether a result may publish. They do not cancel already dispatched storage or provider work.

1. Admit the intended generation and save exact bounded vector IDs and payload bytes before vector dispatch.
2. Record dispatch under the accepted attempt protocol, then insert through the single writer.
3. After a storage timeout or partial result, retry only the same saved IDs and bytes. Do not recompute embeddings or generate fresh IDs for this retry.
4. Read actual records back and verify their identities and contents against the frozen expectation. A global shard count cannot prove exact materialization contents.
5. Publish readiness conditionally only after complete verification and current attempt/retention guards. Partial success remains unready.

The retry spool is bounded temporary infrastructure, not a permanent vector backup. Deterministic saved layout and expected records make verification possible. A semantic reuse key cannot prove that an uncertain numerical execution returned identical vectors.

<a id="separate-model-uncertainty-from-storage-uncertainty"></a>

## Separate model uncertainty from storage uncertainty

A storage retry can reuse already captured bytes. A provider timeout before bytes were captured cannot.

After a provider timeout, it is unknown whether the model processed or billed the embedding request. That timeout does not authorize another paid embedding call. Use the existing durable job uncertainty/recovery contract rather than a hidden retry loop.

A stale worker may still finish remote work after losing authority. Fencing prevents it publishing readiness. It does not undo those side effects. Tombstones and retention protect against late writes to retired identities, using their separate cleanup protocol.

<a id="failure-scope-and-qualification"></a>

## Failure scope and qualification

An uncertain candidate generation does not automatically make an independent healthy serving generation unavailable. Ordinary frozen-payload retries do not require routine Chroma restarts.

Corruption and unresolved cleanup may need intervention. Reconsider a failed backend assumption rather than introducing another engine, distributed coordinator or unbounded work splitting.

These are accepted protocols. Use the guide's backend-contract, failure and resource tests without claiming they ran. Inspect worker/storage adapters before describing a protocol as implemented.

- [Frozen vector retries](#retries), [Indexing qualification](profiles-and-preparation.md), [jobs and idempotency](../../inframeld-application-contracts/references/jobs-and-recovery.md) and [retirement](retirement-and-erasure.md#retirement).
- [ADR-0011](../../../../docs/adr/ADR-0011-retry-frozen-vector-identities-and-payloads.md) explains why retries freeze both identity and payload. [ADR-0010](../../../../docs/adr/ADR-0010-save-deterministic-layouts-for-vector-shards.md) explains saved layouts.

<a id="recover-a-vector-write"></a>

<a id="retries"></a>

<a id="3-recover-a-vector-write"></a>

## Recover a vector write

One component in the **single worker process** creates, inserts, and deletes Chroma data. API handlers and administrative tools must send work through it. They must not write to Chroma independently.

The worker holds one exclusive operating-system file lock for as long as it runs. Every worker uses the same deployment-wide file in the same local Docker volume, so a second worker refuses to start. **Never delete or replace that file to force a takeover.** This arrangement supports one host with local storage.

A timeout means the worker stopped waiting. Chroma may still be processing the request. A PostgreSQL job lease can prevent an old worker from publishing success, but cannot cancel that remote work. Therefore, record each attempt before sending it and limit the size and duration of requests.

<a id="step-1-admit-the-generation-and-save-the-exact-write-batches"></a>

### Step 1: admit the generation and save the exact write batches

Create the generation and its job in PostgreSQL. Keep the generation unavailable to queries while it is being prepared.

Get embeddings through `ModelGateway`. Before writing to Chroma, save the exact IDs, vector numbers, immutable metadata, and any stored text in limited-size batches in private SeaweedFS storage. Give each batch a checksum and save its reference durably. These saved bytes are what a retry will send.

Specify how the numbers are represented and compared, including **float32**, a 32-bit floating-point format. Test those representation rules, called the canonicalization contract, against the selected backend.

If the worker crashes before saving the model's answer, those exact vector bytes are unavailable. Follow the [uncertain model-call rules](../../inframeld-application-contracts/references/jobs-and-recovery.md) instead. Calling the paid model again is a new model call, not a repeat of a saved Chroma write.

<a id="step-2-record-dispatch-then-insert"></a>

### Step 2: record dispatch, then insert

Record that the attempt is about to be sent. Then call Chroma `add` with the saved batch, unique record IDs, and explicit embeddings.

The recorded [Chroma `add` documentation](https://docs.trychroma.com/docs/collections/add-data) says existing IDs are ignored. A duplicate acknowledgement is not proof that the stored values match. Always verify them.

No ordinary path updates a live vector record.

<a id="step-3-retry-only-the-saved-ids-and-bytes"></a>

### Step 3: retry only the saved IDs and bytes

After a timeout, lost response, or worker restart, the default is a bounded automatic retry of the **same IDs and exact payload**. Alternatively, read and verify the expected IDs, then insert the missing ones from that payload.

The retry must not call the embedding model again or send different values under the old IDs.

Set limits on retry delays, attempt count, unresolved requests, and temporary batch storage. That temporary storage is the **retry spool**. An unresolved request is one that might still complete even though the worker has no answer.

When those limits are reached, show the candidate job as failed because its retry budget is exhausted. Routine failures do not require restarting the installation. An explicit [safe resume](../../inframeld-application-contracts/references/jobs-and-recovery.md) keeps the same job ID and saved payload.

<a id="step-4-read-back-and-verify"></a>

### Step 4: read back and verify

Read back the expected records. Check their IDs, count, immutable fields, shard locations, and numerical values using the tested comparison rules. Save which batches passed.

A conflicting existing value is an **integrity failure**, not permission to overwrite it.

Keep a definite failure separate from a request whose outcome is unknown. Even if a retry succeeds, the original request might still be running.

<a id="step-5-publish-readiness-conditionally"></a>

### Step 5: publish readiness conditionally

When every required shard and generation passes, recheck the attempt's ownership, lifecycle, dependencies, and deletion/retention state in one short database transaction. Only then mark the generation or materialization ready.

An old attempt cannot publish after another attempt has replaced it. Each build refers to shared ready generations rather than changing those generations' membership.

<a id="example-one-shard-succeeds-and-the-other-times-out"></a>

### Example: one shard succeeds and the other times out

Suppose inserting b2.1 into S0 succeeds, but the request for b2.2 in S1 times out. M2 stays unready: success on one shard is insufficient.

The worker retries or verifies b2.2 using its saved IDs and numerical bytes, without embedding B2 again. M2 can become ready once both new records and its complete expected scope verify.

If the original S1 request later completes while that record is still present, it encounters the same b2.2 ID rather than replacing it with another value. R1 continues using GA, GB1, GC and does not depend on this candidate's completion.

This behavior must be tested against the pinned backend. Do not assume an entire HTTP batch becomes atomically readable when acknowledged.

<a id="keep-the-retry-spool-temporary"></a>

### Keep the retry spool temporary

Keep a saved batch as long as its generation may need that batch replayed. Delete it only after publication or progress is durably recorded and replay is no longer allowed. To abandon a generation, first retire its identity permanently and disable its retries.

Keep unresolved-attempt identifiers and cleanup evidence even after reclaiming payload bytes.

If a batch disappears or becomes corrupt before verification, show that intervention or explicit abandonment is required. Do not generate new numbers under its old IDs. If published vectors are lost, use [backup/restore or operator intervention](../../../../docs/development/operations/upgrades.md). Rebuilding a lost published index from product records remains deferred. Temporary retry batches are not a complete reconstruction archive.

<a id="an-uncertain-candidate-is-not-a-global-outage"></a>

### An uncertain candidate is not a global outage

A candidate's unresolved insert does not make an older, healthy version unusable or stop unrelated writes. A storage outage, missing published records, or proven corruption does make the affected dependency unavailable. The health checks below distinguish these cases.

Creating or deleting a physical Chroma collection needs its own recovery handling. Give each layout a unique namespace. After an uncertain creation, inspect that exact identity. Never recreate or delete a namespace while live data still refers to it.

<a id="pending-decisions-for-dependent-implementation"></a>

## Accepted decision references for dependent implementation

Apply the accepted contract whose trigger matches. Qualification remains separate from policy approval:

- [PD-INDEXING-04 (accepted): Qualify frozen storage retries and final erasure barriers](decision-storage-retries-and-erasure.md). When implementing frozen-write retry/retirement adapters, selecting artifact completion mechanics or qualifying final-erasure claims.
