# ADR-0004: PostgreSQL authority and immutable Chroma vector generations

**Status:** Accepted — v1 design; implementation and performance qualification pending.  
**Revised:** 19 September 2026.  
**Required approach:** Immutable physical vector generations, PostgreSQL-owned revision membership, and server-owned generation filters. Numerical capacity and performance targets remain provisional.  
**Source:** [Canonical architecture guide](../ARCHITECTURE.md).  
**Related:** [Materializations](ADR-0015-profile-specific-index-materializations-and-pipeline-bindings.md), [authorization](ADR-0005-api-enforced-tenancy-and-authorization.md), [jobs](ADR-0007-durable-jobs-idempotency-and-recovery.md), [backup and restore](ADR-0013-minimal-hosted-observability-and-recovery.md), [retention and deletion](ADR-0014-data-retention-deletion-and-external-processing.md).

## Context

Inframeld needs to search an exact version of a document collection while newer versions are being prepared. Unchanged documents should share their existing vectors rather than be copied or rewritten for every release. At the same time, current permissions must protect both old and new content.

The starting point is to separate **which records belong to a version**, **where their searchable vectors are stored**, and **whether the caller may access them now**. These are related facts, but they do not belong in one mutable field on every vector.

Failures make that separation important. A request to insert vectors can reach Chroma even when its response never reaches the worker. Retrying must not replace historical numerical values, expose a partly built index, or unnecessarily interrupt a healthy release. Deletion has a different difficulty: an earlier request can still finish after a record was deleted.

This ADR defines ownership, identities, build and query behavior, retries, and cleanup for the supported single-host deployment. It also defines the tests needed before claiming that the design works at a particular scale.

## Decision

**PostgreSQL owns application state and decides which exact vector generations a query may search. Chroma stores immutable derived vector records. The application builds the search filter from exact collection membership and current permissions.**

A new collection revision does not add its ID to every Chroma record. Compatible revisions share unchanged records, while new numerical output gets a new physical identity.

This removes membership-related writes to unchanged vectors and provides an exact-payload retry path. It does not turn PostgreSQL and Chroma into one transaction, make large queries automatically cheap, or prove physical erasure while an old external request remains unresolved.

### 1. Vocabulary: a logical collection is not a Chroma collection

The word **collection** has two meanings. An Inframeld collection is a managed set of documents. A physical Chroma collection is a storage and search container for vectors. They do not have a one-to-one relationship.

An **embedding** is a numerical representation of text used for similarity search. A vector record stores that representation and the information needed to identify its source chunk.

| Term                                   | Meaning                                                                                                                                                                                       | Example used below                                                                 |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| **Document / document version**        | A stable source identity and one immutable version of its bytes. Updating the source creates another version.                                                                                 | Document B has versions B1 and B2.                                                 |
| **Chunk / vector record**              | A chunk is an excerpt produced by parsing and splitting source content. Its vector record contains the numerical embedding and immutable identifiers needed to locate and verify the excerpt. | A1 produces two chunks, represented by a1.1 and a1.2.                              |
| **Logical collection**                 | The application's name for a managed corpus: the body of documents used together.                                                                                                             | Collection L contains the team's manuals.                                          |
| **Collection revision**                | An exact, immutable membership snapshot. It does not follow each document's newest version.                                                                                                   | R1 contains A1, B1, C1; R2 contains A1, B2, C1.                                    |
| **PostgreSQL membership**              | The authoritative record of which document versions belong to a revision. Large lists may be held in referenced immutable manifests.                                                          | R1 still names B1 after R2 exists.                                                 |
| **Immutable vectorization generation** | The exact numerical output for all chunks of one document processing generation under one embedding profile. Its physical identity is never reused.                                           | GB1 contains B1's two vectors; GB2 contains B2's two new vectors.                  |
| **Application vector index**           | An organization/project-scoped, profile-specific search resource. The vector-index adapter hides its physical layout.                                                                         | Index I uses embedding profile E1.                                                 |
| **Physical Chroma collection / shard** | One physical partition of an application vector index, not a logical revision or replica.                                                                                                     | S0 and S1 are shards of I. Each record goes to one shard.                          |
| **Layout**                             | The saved placement rule and physical shard references. It determines where records belong and which shards must be searched.                                                                 | LAYOUT1 uses S0 and S1. R2 does not create another layout.                         |
| **Index materialization**              | A verified mapping from an exact revision and its processing/embedding profiles to the physical generations needed in a layout.                                                               | M2 establishes that R2 uses GA, GB2, GC and that its required records are present. |
| **Query filter**                       | A restriction built by the server from exact membership and current permissions.                                                                                                              | R2 permits GA, GB2, GC; a caller forbidden B permits only GA, GC.                  |

An **embedding profile** fixes vector meaning, including the model, dimensions, and distance metric. A **processing profile** fixes how source bytes become chunks.

A **manifest** is an immutable inventory of expected identities, locations, counts, and fingerprints. A fingerprint or hash helps verify content; it cannot recreate missing numerical embeddings.

These definitions describe the design. They are not additional features or evidence of tested capacity.

### 2. Storage and module responsibilities

| Component                             | Responsibility                                                                                                                                                                                    |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **PostgreSQL**                        | Owns document identities and versions, exact collection revisions, authorization, vector-generation references, materialization readiness, jobs, release pointers, retention, and deletion state. |
| **Chroma**                            | Stores immutable derived vector records and searches the scope selected by the application. It does not own logical membership or permissions.                                                    |
| **SeaweedFS through `ArtifactStore`** | Provides private S3-compatible artifact storage, including referenced manifests and temporary exact retry payloads. PostgreSQL owns their identity and publication.                               |
| **`ModelGateway`**                    | Supplies every document and query embedding. Chroma receives explicit embeddings and must not invoke its own provider embedding function.                                                         |

In production Docker Compose, Chroma runs as a **private HTTP server**. Clients must not open a shared embedded persistence directory.

Domain code depends on the application ports `ArtifactStore` and `VectorIndex`, not vendor clients. A port is the application's interface for a capability; an adapter implements it using a particular storage product.

The **Indexing** business area owns processing generations, vector generations, layouts, and materialization readiness. **Pipelines** owns immutable pipeline bindings. Application use cases coordinate them; another module must not maintain a competing readiness flag.

Status views can read PostgreSQL projections directly. This is lightweight CQRS: reads have useful shapes without loading an entire corpus into a domain object merely to display its status.

### 3. Profiles, identity, and safe reuse

#### Profiles describe behavior, not just names

An immutable embedding profile identifies its organization/project, gateway and semantic configuration revision, model alias, dimensions, normalization, and distance metric.

A change that can alter vector meaning creates a new profile. Credential rotation alone does not, provided the semantics remain unchanged.

An immutable processing profile identifies parser/chunker behavior and implementation. Its processing generation identifies the resulting chunks.

#### Keep compatibility separate from physical execution

| Identity                              | Purpose                                                                                                                                                                          |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Semantic reuse key**                | Organization/project + document version + processing generation + embedding profile. It finds compatible, healthy, ready work without another model call.                        |
| **Physical vectorization generation** | One immutable numerical execution, or incarnation, for that key. It has a unique, never-reused generation ID, an exact manifest, and frozen write batches.                       |
| **Physical record ID**                | A versioned, deterministic encoding or hash of organization/project + vectorization-generation ID + chunk ID. The generation ID is part of the **record ID**, not only metadata. |

**A fresh model response must never overwrite a retained generation.** Different numerical output requires a new physical generation and therefore different record IDs, even when the semantic reuse key is unchanged.

Logical collection and pipeline IDs are not part of vector identity. Compatible collections and pipelines can therefore share the same physical records.

PostgreSQL serializes admission for each reuse key: it reuses a ready generation, attaches work to an already-admitted build, or admits one new attempt. **Admission** means durably accepting the work. An attempt that loses SQL ownership cannot publish its result. Unreferenced attempts become cleanup work; they are not implicitly selected for serving.

Each Chroma record contains explicit embeddings, immutable chunk content or a content reference, and immutable scope/profile/document/generation/chunk metadata. It contains **no mutable revision membership, permission-group list, or serving flag**.

Generation state and manifests are tracked in PostgreSQL. A database row for every vector is unnecessary. Large manifests and artifacts are streamed in bounded pages rather than loaded all at once.

### 4. Physical layout and sharding

One application vector index belongs to an organization, project, and embedding profile. Its immutable layout records the placement-algorithm version, fixed shard count, and physical shard references.

The physical namespace includes:

```text
organization_id + project_id + embedding_profile_id + layout_id + shard_id
```

Placement uses the recorded layout and deterministic record identity. A process-local hash or the current number of containers is not a placement rule.

**Changing the layout is a deliberate migration, not an environment-variable edit.** Do not create a Chroma collection for every logical collection, revision, or pipeline.

The same bounded write, verification, and query paths work with one or several shards. Qualification must include at least two.

In the supported deployment, both shards are Chroma collections **inside the same server on the same host**. They are partitions, not replicas: a record in S0 is not automatically copied to S1. They share RAM, CPU, and the same server/host failure boundary. Two shards provide neither high availability nor twice the machine's capacity.

Automatic re-sharding, multiple writer hosts, distributed Chroma operation, and Kubernetes support are deferred. The adapter boundary and saved layout provide a place for future migration work; they do not make a backend change free.

### 5. Worked example: one changed document and two retained revisions

All documents in this example belong to organization O1/project P1. They use processing profile PP1, embedding profile E1, index I, and LAYOUT1. Each document version produces exactly two chunks.

The short labels stand in for real opaque IDs. The illustrated shard assignments are outputs of the recorded placement rule, not a requirement to put one chunk from every document in each shard.

#### Authoritative application state

Collection L initially has revision R1. Document B changes from B1 to B2, creating revision R2.

These are conceptual records and inventories, not a prescribed SQL schema. Large immutable inventories may live in SeaweedFS manifests whose identities and publication PostgreSQL owns.

| Application record or manifest    | R1                                                       | R2 after verification                                                           |
| --------------------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------- |
| **Logical collection**            | L                                                        | The same L.                                                                     |
| **Exact membership**              | A1, B1, C1.                                              | New membership A1, B2, C1. R1 is unchanged.                                     |
| **Selected physical generations** | M1 maps A1 → GA, B1 → GB1, C1 → GC.                      | M2 maps A1 → GA, B2 → GB2, C1 → GC.                                             |
| **Profiles and layout**           | PP1 / E1 / I / LAYOUT1.                                  | The same PP1 / E1 / I / LAYOUT1.                                                |
| **Expected chunks**               | GA: a1.1, a1.2; GB1: b1.1, b1.2; GC: c1.1, c1.2.         | Reuse GA and GC; use GB2: b2.1, b2.2 instead of GB1 **in M2's inventory only**. |
| **Readiness evidence**            | M1 is ready after its six expected records are verified. | M2 becomes ready only after its six expected records are verified.              |
| **Pipeline binding**              | P-V1 binds M1.                                           | P-V2 binds M2. This does not promote P-V2.                                      |

#### Physical storage

S0 and S1 already exist. R2 inserts two records into them; it does not create an R2 Chroma collection. The final column explains the timeline and is not stored as mutable Chroma metadata.

| Record | Immutable generation | Source chunk | Shard | Why it is present                  |
| ------ | -------------------- | ------------ | ----- | ---------------------------------- |
| a1.1   | GA                   | A1, chunk 1  | S0    | Inserted for R1; unchanged for R2. |
| a1.2   | GA                   | A1, chunk 2  | S1    | Inserted for R1; unchanged for R2. |
| b1.1   | GB1                  | B1, chunk 1  | S1    | Retained while R1 is needed.       |
| b1.2   | GB1                  | B1, chunk 2  | S0    | Retained while R1 is needed.       |
| c1.1   | GC                   | C1, chunk 1  | S0    | Inserted for R1; unchanged for R2. |
| c1.2   | GC                   | C1, chunk 2  | S1    | Inserted for R1; unchanged for R2. |
| b2.1   | GB2                  | B2, chunk 1  | S0    | Newly inserted for R2.             |
| b2.2   | GB2                  | B2, chunk 2  | S1    | Newly inserted for R2.             |

There are **six records before the change, eight while both revisions are retained, and six after GB1 can safely be removed**.

GA and GC are not duplicated or given another membership field. Their values, metadata, IDs, and placement remain unchanged. R1 can retrieve B1 while R2 retrieves B2 because the application selects different generation filters over the same physical shards.

#### Separate the build and release steps

| Phase                    | Application / PostgreSQL work                                                                                  | Processing, model, or Chroma work                                                                                                    |
| ------------------------ | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **Admit B2 and R2**      | Store the source version and exact R2 membership; request M2 as unready.                                       | No existing vectors change.                                                                                                          |
| **Prepare missing work** | Resolve reuse keys, select GA/GC, admit GB2, and record bounded progress and frozen payload references.        | Parse/chunk B2 in the isolated processor; obtain two embeddings through `ModelGateway`; insert b2.1/b2.2 into their recorded shards. |
| **Verify M2**            | Read the expected six-record inventory and check dependencies.                                                 | Verify the new numerical records; check expected IDs, immutable metadata, and placement for all six records, including GA/GC.        |
| **Publish readiness**    | Conditionally mark M2 ready after every required check passes.                                                 | No membership metadata update.                                                                                                       |
| **Evaluate and release** | Evaluate P-V2; authorized commands attach it, enable a canary, or promote its Deployment pointer.              | Queries use the selected version's filter. Promotion itself writes no vectors.                                                       |
| **Retire R1 ordinarily** | Wait for deployment, build, rollback, and query references to end; revoke unused GB1's reuse and tombstone it. | Delete b1.1/b1.2 when safe. Do not write to GA/GC.                                                                                   |

A **tombstone** permanently marks a physical identity as retired so it cannot be reused or made live again. The full retirement protocol appears below.

Creating a revision, materializing it, publishing readiness, and promoting a pipeline are separate transitions. The durable build request freezes its configuration, exact revisions, and profiles; it never follows a changing “latest” value while running.

A pending build may reserve a future pipeline-version ID. The complete immutable pipeline and its ready bindings are published only after every required materialization is ready.

A prompt-only pipeline version can reuse M1 without another physical collection or vectorization. Retaining R1 does not preserve old access rights: current permissions can exclude B from either revision.

### 6. Verify the materialization, not the shard's global count

Each materialization records expected and verified immutable manifest hashes, vector counts, per-shard progress, and publication state.

A **new generation** must be checked against its frozen numerical payload before publication. Initially, every **new materialization** also makes a bounded full pass over its expected record IDs, immutable metadata, and placement.

Already-verified numerical-generation evidence can be reused for a membership-only release. This avoids downloading every numerical coordinate again merely because membership changed. Targeted integrity checks still inspect actual bytes. **A hash stored in Chroma metadata is not, by itself, proof that the vector matches it.**

Missing records, incompatible profiles, wrong placement, or fingerprint conflicts block publication.

Unrelated generations in a shared shard are normal. M2 expects six records even though S0 and S1 contain eight while R1 is retained. A global Chroma count of eight proves neither that M2 is wrong nor that all six of its required records exist.

#### Bounded memory does not mean constant total work

Let **D** be the number of document-version memberships and **N** the number of chunks being materialized. O(D) and O(N) describe work that grows with those counts.

Logical snapshot assembly can read or copy O(D) memberships. Verification can read O(N) records even when only one document changed. Query authorization and filter construction also grow with the permitted-generation set.

Bounded pages limit memory per step; they do not remove the total work. **Only changed chunks need new Chroma inserts, but total release time is not necessarily proportional to the number of changed documents.**

### 7. One writer, with retries of the exact saved payload

#### One component owns physical changes

One vector-writer component inside the **single worker process** owns physical provisioning, insertion, and deletion. It is not another service or container. API handlers and administrative tools must not independently mutate Chroma.

The worker holds an exclusive operating-system file lock for its entire lifetime. The lock uses one deployment-wide file in the same local Docker volume. A second worker refuses to start. **Never delete or replace the lock file to force takeover.** This contract applies to one host and local storage.

Writer requests are bounded, but a request may still be active in Chroma after the client times out. PostgreSQL leases protect job and publication ownership; they do not stop an external Chroma request. Durable attempt evidence must therefore be recorded before dispatch.

#### Step 1: admit the generation and save the exact write batches

Admit a generation and job in PostgreSQL. The generation is not yet available for serving.

Obtain embeddings through `ModelGateway`. Before sending anything to Chroma, seal bounded, checksummed batches in private SeaweedFS storage. Each batch contains the record IDs, numerical coordinates, immutable metadata, and any stored text. Record each batch reference durably.

The coordinates follow a defined **float32/canonicalization contract**: the agreed numerical representation and rules for writing and comparing those values. That contract must be qualified against the selected backend.

If the worker crashes before capturing a model-provider result, the separate ambiguous-provider-call policy applies. Silently making another paid model call is not an exact retry of a saved vector write.

#### Step 2: record dispatch, then insert

Persist the dispatch attempt, then use Chroma `add` with the frozen payload. Every batch contains unique IDs and explicit embeddings.

The recorded [Chroma `add` documentation](https://docs.trychroma.com/docs/collections/add-data) says existing IDs are ignored. A duplicate acknowledgement is not proof that the stored values match; always verify them.

No ordinary path updates a live vector record.

#### Step 3: retry only the saved IDs and bytes

After a timeout, lost response, or worker restart, the default is a bounded automatic retry of the **same IDs and exact payload**. Alternatively, read and verify the expected IDs, then insert the missing ones from that payload.

The retry must not call the embedding model again or send different values under the old IDs.

Bound the backoff, attempt count, outstanding ambiguous attempts, and retry-spool bytes. The **retry spool** is temporary storage for these saved batches. An ambiguous attempt is one whose external completion is still unknown.

When the budget is exhausted, leave the candidate job visibly failed with an exhausted-budget reason. Do not require a deployment-wide restart. An explicit safe resume follows [ADR-0007](ADR-0007-durable-jobs-idempotency-and-recovery.md), preserving the frozen payload and job identity.

#### Step 4: read back and verify

Read the expected records and check identities, count, immutable fields, placement, and numerical coordinates under the qualified canonicalization contract. Persist verified batch progress.

A conflicting existing value is an **integrity failure**, not permission to overwrite it.

Keep definitive errors distinct from unresolved external attempts. A successful duplicate retry does not prove that the original request has finished.

#### Step 5: publish readiness conditionally

After every required shard and generation is verified, use a short conditional SQL transaction to recheck attempt ownership, lifecycle, dependencies, and deletion/retention state. Only then mark the generation or materialization ready.

A superseded attempt cannot publish. Builds reuse ready shared generations; they do not acquire private mutable membership arrays.

#### Example: one shard succeeds and the other times out

Suppose inserting b2.1 into S0 succeeds, but the request for b2.2 in S1 times out. M2 stays unready: success on one shard is insufficient.

The worker retries or verifies b2.2 using its saved IDs and numerical bytes, without embedding B2 again. M2 can become ready once both new records and its complete expected scope verify.

If the original S1 request later completes while that record is still present, it encounters the same b2.2 ID rather than replacing it with another value. R1 continues using GA, GB1, GC and does not depend on this candidate's completion.

This behavior must be tested against the pinned backend. Do not assume an entire HTTP batch becomes atomically readable when acknowledged.

#### Keep the retry spool temporary

Retain a batch while its generation can require replay. Reclaim it only after publication/progress is durable and no further replay of that batch is allowed. If abandoning the generation, tombstone it and disable retries first.

Keep unresolved-attempt identifiers and cleanup evidence even after reclaiming payload bytes.

A missing or corrupt spool before verification requires visible intervention or explicit abandonment, not a new model response under old IDs. Missing published vectors require backup/restore or intervention. Product-level index reconstruction remains deferred under ADR-0013; the spool is not a retained reconstruction archive.

#### An uncertain candidate is not a global outage

An uncertain insert into a candidate does not invalidate healthy ready generations or globally block unrelated writes. A backend outage, missing published records, or demonstrated corruption does make the affected dependency unavailable. Its health must be captured and rechecked as described below.

Provisioning and deleting physical collections are separate from record retries. Use unique layout namespaces, inspect ambiguous provisioning by identity, and never recreate or delete a namespace still referenced by live data.

### 8. Query only the exact, currently authorized generations

For each query, the application follows this sequence:

1. **Authenticate and select the pipeline.** Authenticate a Kratos user or scoped service principal, check project/action access, and resolve the Deployment and immutable PipelineVersion. A service principal is the application's authenticated identity for an integration.
2. **Protect the operation's dependencies.** Admit a bounded operation pin and resolve healthy, ready profile/layout/materialization dependencies in PostgreSQL. A pin prevents ordinary cleanup from removing resources while the operation uses them.
3. **Compute the permitted generations.** Take the compatible generation union from the pipeline's exact revisions, intersect it with current document group allowlists and deletion state, and deduplicate it.
4. **Embed the question.** Obtain one query embedding for the selected profile through `ModelGateway`.
5. **Build the filter on the server.** Include `vectorization_generation_id: {"$in": [...]}` and the required immutable scope/profile constraints.
6. **Search and merge.** Query every required shard with bounded concurrency and a common deadline. Merge using the same metric, stable record-ID tie-breaking, and overlap deduplication.
7. **Verify before using or releasing content.** Check returned identities/content references, current document permissions, and dependency health before text reaches a reranker, evaluator, model, or client. Check again before releasing the result.

#### The worked example's searchable sets

“Eligible records” means records Chroma may consider. A nearest-neighbor query still returns only its bounded requested candidates, not every eligible record.

| Revision and current permissions | Generation filter | Eligible in S0   | Eligible in S1   |
| -------------------------------- | ----------------- | ---------------- | ---------------- |
| R1; A, B, C permitted            | GA, GB1, GC       | a1.1, b1.2, c1.1 | a1.2, b1.1, c1.2 |
| R2; A, B, C permitted            | GA, GB2, GC       | a1.1, b2.1, c1.1 | a1.2, b2.2, c1.2 |
| R2; B forbidden                  | GA, GC            | a1.1, c1.1       | a1.2, c1.2       |
| R2; nothing permitted            | Empty             | No query         | No query         |

For the fully authorized R2 query, the adapter can construct this internal Chroma filter:

```json
{
  "$and": [
    { "organization_id": { "$eq": "O1" } },
    { "project_id": { "$eq": "P1" } },
    { "embedding_profile_id": { "$eq": "E1" } },
    { "processing_profile_id": { "$eq": "PP1" } },
    { "vectorization_generation_id": { "$in": ["GA", "GB2", "GC"] } }
  ]
}
```

**The caller does not submit this authoritative filter.** The server builds it from verified application state.

Send the same query embedding and permitted scope to **both S0 and S1** in LAYOUT1. One generation's chunks may occupy several shards; naming a generation does not place all its records in one shard.

If B is forbidden, the server changes the `$in` list to GA, GC. No Chroma metadata write is needed. GB1 is excluded from R2 even for an authorized B reader because it is not part of R2's generation set.

#### Merge comparable candidates, then verify them

Suppose the query needs two final candidates without reranking. Ask each shard for up to two candidates within the exact filter. Using the same cosine-distance metric, the illustrative results are:

| Shard | Candidates, smaller distance first |
| ----- | ---------------------------------- |
| S0    | b2.1: 0.08; a1.1: 0.15             |
| S1    | c1.2: 0.06; b2.2: 0.20             |

Merge, deduplicate record IDs, and use stable ID ordering for ties. The final two are **c1.2 and b2.1**. Verify their authoritative identities and current permissions before using the text.

These distances are invented examples, not benchmark results. HNSW is the single-node approximate-nearest-neighbor index: filtering selects the exact allowed corpus, but approximate search can still miss true nearest neighbors. Qualification must measure recall, the fraction of relevant nearest results recovered.

**If S1 fails, the query is unavailable.** Do not present S0's results as though the entire required corpus was searched.

#### Empty or invalid filters must never become unrestricted searches

An empty allowed set returns an authorized no-evidence outcome without querying Chroma.

Never omit a failed or empty filter. Do not retrieve global top-k results and rely only on discarding forbidden results afterward: forbidden or obsolete records can crowd out the permitted candidates before they are retrieved.

Checks on the bounded returned result are defense in depth **in addition to** the search filter, not a replacement for it.

#### Permissions remain current

Group membership and document allowlists stay in PostgreSQL. Fixed integration access uses the service principal's assigned groups. A supplied `userId` or canary affinity key cannot expand that authority. Authentication does not make Chroma metadata the permissions authority.

Immutable manifests can be cached. Any cache of authorized generations must include and revalidate current permission/group revisions. Revocation applies to historical collection revisions too. ADR-0005 owns this access-policy boundary; the vector adapter does not add another policy engine.

Perform a final current-policy check **after queue or budget waits and immediately before handing content to an external client or response writer**.

A revocation committed before that check denies the send. A revocation racing after the check can overlap the already-admitted send, which cannot be recalled. Subsequent checks must stop further dispatch or release when they observe revocation. PostgreSQL authorization and network delivery are not one atomic action.

#### Bound the combined query scope

Bounds cover allowed-generation count, serialized filter bytes, predicate count, shard fan-out, candidates, and deadline. A pipeline selecting multiple collections must fit the **combined** allowed-generation bound.

Unsupported scope fails explicitly. Do not automatically send a million IDs or start an unbounded loop splitting the filter into smaller searches. A future partitioned-filter implementation would need complete coverage, sufficient candidates per partition, and measured merged recall. It is not part of this initial design.

The MVP permits one processing profile and one embedding profile per pipeline. Combining scores from mixed profiles is deferred.

### 9. Pins, retirement, and physical erasure

#### Coordinate query admission with retirement

Resolve the target and register its operation/pipeline pin in one short PostgreSQL transaction, using the same retention lock or conditional revision as retirement. This **retention gate** prevents a reader from appearing between the reference check and disposal.

A reader cannot pin an already-retiring binding. Garbage collection, or **GC**, cannot dispose of a binding while a reader is admitted. Deployment, candidate, build, retained rollback, and query pins all count. Promoting another version does not move an existing query to that version.

Pins end on terminal completion. An abandoned pin expires only after an **enforced request deadline** prevents further reads or outbound content and discards late results.

If termination cannot be established, retain the pin or conclusively stop/drain the old query runtime before reclaiming it. A timeout recorded in the database is not enough if the old operation can still read or disclose content.

Explicit erasure or revocation overrides ordinary retention and makes affected operations fail safely.

#### Recheck dependency health during the operation

Each dependency has a **health generation**, a revision used to detect health changes. It changes on corruption, unavailability, and recovery, not on harmless candidate insertion.

Capture it at admission. Recheck after retrieval, before provider dispatch, and before result release. Discard results if it changes.

These checks do not make remote calls atomic with SQL, and already-sent text cannot be recalled.

#### Retire physical identities before deleting their records

Before ordinary deletion, atomically revoke generation reuse, prove its references have ended under the retention gate, and permanently tombstone its physical identity. That identity can never become live again or be reused by another attempt.

Delete using explicit record/generation IDs from the manifest. Broad deletion based on mutable scope is forbidden.

Tombstones and job state prevent new application retries. They do **not** cancel an external request already accepted by Chroma.

In the example, promoting P-V2 does not immediately delete GB1. R1 may still be the rollback target, another pipeline may bind M1, or a query may still be using it. After all ordinary references end, GB1 can be tombstoned and its two records removed. GA and GC stay because M2 still needs them.

Removing one user's B access changes that user's filter at the documented authorization boundary. It does not require deleting shared vectors that other authorized users still need.

**Explicit erasure of B is different:** first invalidate all affected serving dependencies, then remove B's owned generations under the deletion protocol rather than preserving them solely for rollback.

#### Logical revocation is not proof of physical cleanup

A delayed old `add` can finish **after deletion** and recreate an unreachable record. Exact PostgreSQL-selected generation filters keep that tombstoned generation out of every query.

However, a successful delete and one absence check cannot prove final erasure while the original request remains unresolved. Report:

> Logical access revoked / physical cleanup pending.

Retain attempt evidence, retry cleanup within bounds, and alert on backlog or disk limits. Do not report completed erasure or discard evidence merely because a duplicate insertion succeeded.

For example, b2.2's first request times out, its retry succeeds, and R2 eventually becomes unused. GC retires and deletes GB2. If the original S1 request then finishes, it may insert b2.2 again because the ID is absent.

GB2 remains tombstoned and cannot enter a query filter or new build. User access is not restored, but physical deletion is not yet proven. This cleanup problem does not invalidate the earlier exact-payload retry while GB2 was live.

Delayed artifact or spool uploads need the same honest cleanup status under ADR-0014. A PostgreSQL tombstone does not cancel an in-flight SeaweedFS `PUT` either.

#### Exceptional cleanup needs a tested completion barrier

Final cleanup of unresolved writes requires proven server completion or **quiescence**—a state in which old work can no longer overtake cleanup—or qualified backend preconditions.

On the supported single server, an exceptional maintenance procedure may stop the old writer, confirm its exit, stop/restart Chroma, establish recovery and ordering of already-accepted log work, then delete and verify retired IDs before marking cleanup complete.

The pinned-server failure test must establish that old work cannot run after this cleanup. Restarting only the client is insufficient. A Cloud adapter needs a supported equivalent; the local procedure does not apply to managed queues.

This is exceptional final cleanup, not the response to every lost build response.

Persistent storage failure, identity/hash conflicts, missing published data, corrupt unfinished spool, or cleanup backlog reaching its bound also require intervention. Automatic retries handle routine transient failures, not every possible fault without an operator.

### 10. Recorded Chroma evidence and its limits

The following findings were recorded on **19 September 2026**. They describe that inspection, not completed Inframeld qualification or a guarantee about future backend versions.

#### Release and client behavior

The recorded inspection identified **Python/server release 1.5.9**, built **5 May 2026**, as the latest stable release verified in PyPI and the project release list. It identified the rolling `latest` release as a development prerelease.

That observation is neither a production image lock nor an exhaustive registry guarantee. Qualification must pin a supported image digest and matching SDK. Do not use floating `latest`.

References: [PyPI](https://pypi.org/project/chromadb/), [release 1.5.9](https://github.com/chroma-core/chroma/releases/tag/1.5.9), [project releases](https://github.com/chroma-core/chroma/releases).

The recorded query evidence shows explicit `ids` and metadata filtering, including scalar `$in` restrictions on searched records. Generation filters avoid sending every chunk ID, but their large-list cost remains unmeasured.

References: [query API](https://docs.trychroma.com/docs/querying-collections/query-and-get), [metadata operators](https://docs.trychroma.com/docs/querying-collections/metadata-filtering), [1.5.9 Collection source](https://raw.githubusercontent.com/chroma-core/chroma/1.5.9/chromadb/api/models/Collection.py).

#### Conditional transactions are not a dependency of this design

The rolling documentation inspected for this ADR describes collection-scoped conditional transactions with read-check-write conflict detection. `conditional()` was absent from the inspected 1.5.9 client and present in `main`.

Those transactions do not span shards. Filter reads protect returned IDs, not records that match later. Availability, absence/tombstone semantics, and ambiguous-commit behavior need separate qualification.

This design does not depend on conditional transactions. It also does not claim that Chroma has no such capability.

References: [conditional transactions](https://docs.trychroma.com/docs/collections/conditional-transactions), [main Collection source](https://raw.githubusercontent.com/chroma-core/chroma/main/chromadb/api/models/Collection.py).

#### Single-node and Cloud behavior must not be conflated

The recorded evidence distinguishes single-node HNSW indexes from Cloud/distributed SPANN indexes. The active HNSW working set needs RAM across concurrently used collections; more collections do not add host RAM. The vendor's older workload/latency table is not an Inframeld benchmark.

The recorded **Cloud** quotas are 5 million records per collection, 300 records per write, 10 concurrent reads and 10 concurrent writes per collection, and at most 8 `where` predicates. These are not universal open-source limits and do not establish an unlimited `$in` payload size.

Cloud collection forks can share storage; single-node does not support that feature. The pinned client's hybrid `search` is experimental and hosted/distributed-only. Neither feature is required for this open-source release-history design.

References: [collection configuration](https://docs.trychroma.com/docs/collections/configure), [single-node performance](https://docs.trychroma.com/guides/performance/single-node), [Cloud limits](https://docs.trychroma.com/cloud/quotas-limits), [collection forking](https://docs.trychroma.com/cloud/features/collection-forking), [pinned client source](https://raw.githubusercontent.com/chroma-core/chroma/1.5.9/chromadb/api/models/Collection.py).

#### A million documents is not the qualified capacity

One million documents averaging 20 chunks produce 20 million vectors. At 1,536 float32 dimensions, their coordinates alone occupy **122.88 GB decimal, approximately 114.4 GiB, per profile**. Metadata, index overhead, and the other services require additional space and memory.

The proposed 64 GiB qualification host below is not a million-document capacity promise. Larger hardware may help, but O(D) authorized-generation construction and filter payload size can still require a different adapter strategy. Working sharding and ports avoid a domain rewrite; they do not make that later engineering trivial.

### 11. Provisional qualification environment and workload

**Everything in this section is a planning assumption, not measured capacity, a supported limit, or a service-level agreement.**

Use one Linux server with **16 vCPUs, 64 GiB RAM, and 1 TB usable local SSD/NVMe storage**, plus off-host backups. Run one Chroma server with two fixed shards. Model inference runs remotely or through the customer's gateway; local language-model memory is excluded.

#### Proposed memory allocation

| Component                             | Planning budget |
| ------------------------------------- | --------------- |
| Chroma                                | 32 GiB          |
| PostgreSQL                            | 6 GiB           |
| Parser, one attempt                   | 8 GiB           |
| SeaweedFS                             | 4 GiB           |
| API, worker, console, and ingress     | 4 GiB           |
| Kratos                                | 1 GiB           |
| Operating system, cache, and headroom | 9 GiB           |
| **Total**                             | **64 GiB**      |

#### Proposed workload

| Dimension                | Initial target and stress variants                                                                                                                                              |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Corpus**               | 25,000 current documents averaging 20 chunks: 500,000 current vectors. Test stages at 1,000, 10,000, then 25,000 documents; run a deliberate 50,000-document stress experiment. |
| **Sources and text**     | Average source size 0.5 MiB; average chunk text 2 KiB. Test unusually large inputs with explicit per-source limits.                                                             |
| **Profiles**             | One active 1,536-dimensional float32 profile. A second profile is a separate stress experiment.                                                                                 |
| **Retention and change** | Three retained collection revisions; daily changes to 1% of documents at stable document count. Additional pins/builds consume admission budget.                                |
| **Permissions**          | 20 groups; a typical user belongs to two. Test permitted fractions of 100%, 50%, 1%, and 0%, including permission changes during queries.                                       |
| **Filters and metadata** | Measure against a metadata target of at most 1 KiB per record. A list of 25,000 UUID-style generation IDs is roughly 1 MB of JSON per shard, not a verified backend allowance.  |
| **Work**                 | Initial ingestion target of one document per second. One build and one evaluation at a time, sharing resource limits with serving.                                              |
| **Queries**              | Five concurrent end-to-end requests. Also test concurrency of 1 and 10, plus controlled arrival rates that expose queueing.                                                     |

#### Storage and time calculations are not total-resource predictions

With equal-sized, distinct 1% changes between three retained revisions, their union is approximately **510,000 vectors**, not three complete copies. Their coordinates occupy **3.13344 GB decimal / approximately 2.92 GiB**. Three full physical snapshots would require approximately **9.216 GB** of coordinates.

Extra profiles, larger changed documents, retained pins, and failed-attempt cleanup increase storage. At the assumed source size, current sources occupy about **12.2 GiB before old versions**. One copy of 510,000 chunks at 2 KiB is about **1 GiB**.

Parsed artifacts, PostgreSQL's write-ahead log (WAL), indexes, duplicate text, retry spool, scratch space, and backups are additional. These calculations do not predict total consumption.

At one document per second, 25,000 documents take at least approximately **6.9 hours**, before slower phases or queues. A 1% change adds about **250 documents / 5,000 chunks** to process, but full manifest/verification reads and query authorization still involve the larger corpus.

### 12. Qualification tests and stopping rules

Run these tests against pinned images and a recorded host, corpus, and workload. They are requirements before making production claims, **not tests completed by writing this ADR**.

#### Backend contract

Prove duplicate `add` behavior, partial completion, read visibility, restart durability, and float32 read-back verification with explicit embeddings.

Drop responses before and after the backend applies a request. Replay frozen batches in different orders and terminate workers between every durable step.

Pass only if published bytes never change, partial materializations never become available for serving, and healthy old releases continue without routine Chroma restarts.

**If the assumed backend contract fails, stop and reconsider the adapter/protocol. Do not hide the failure inside a larger retry loop.**

#### End-to-end lifecycle

Ingest, verify, publish, and back up R1. While serving queries, change one document at corpus sizes of 1,000, 10,000, and 25,000, then test random and localized 1% changes.

Build, verify, and evaluate R2; exercise canary, promotion, and rollback; retire R1 after its pins end; and measure cleanup and compaction, the storage work involved in reclaiming deleted data.

Count all PostgreSQL, artifact-store, and Chroma reads and writes. **Membership-only changes must issue zero writes to surviving vector records.** Record the full verification and snapshot costs that remain.

#### Security and failures

Test forged scope/group input, zero permitted generations, revocation during queries, failed shards, stale SQL publication, query-pin-versus-GC races, and delayed insertion after deletion.

Pass only with no content outside the scope authorized at the final dispatch/release check, explicit failed-shard outcomes, no readmission of deleted generations, and cleanup-pending evidence retained until a tested completion barrier.

Test the permission boundary at all three points: revocation before a dispatch check denies the send; revocation after that check has the documented already-admitted-send race; revocation before the response check suppresses the response. Successful replay must not falsely mark physical erasure complete.

#### Resources and performance

Record phase duration, resident-memory and container-memory peaks, CPU use, disk/WAL/spool growth, queue age, provider usage, serialized filter size, and PostgreSQL authorization work.

Measure filtered approximate-nearest-neighbor latency at **p50, p95, and p99** and **recall@k** against an exact, correctly scoped reference on a representative fixture. Percentiles describe the latency distribution; recall@k measures how many of the exact reference's top-k neighbors the approximate search recovers.

Report model/judge time separately. Include warm and cold queries and a build running under query load.

Resource budgets must reject admission visibly **before** out-of-memory failure, sustained swapping, or an unbounded backlog.

#### Provisional go/no-go goals

| Measurement                                                             | Proposed goal                                                          |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| **Database retrieval, including authorization and filter construction** | p95 at most 1 second at five concurrent requests during a small build. |
| **Retrieval quality**                                                   | recall@10 of at least 0.95 on the declared fixture.                    |
| **One-document release platform overhead**                              | At most 2 minutes.                                                     |
| **1% change platform overhead**                                         | At most 15 minutes.                                                    |

Report parser/model time and complete end-to-end time separately. These goals remain proposals for qualification, not accepted capacity claims.

If the 25,000-generation filter or its payload limit fails, or measured latency misses the goal, lower the qualified workload or reconsider the adapter before advertising support. Do not silently remove scope predicates, expand bounds indefinitely, or add segment/compaction infrastructure merely to preserve an unproven target.

### 13. A modest local trial is a separate, untested recommendation

For first local use, the proposed trial is a **16 GiB laptop with 4 CPUs and 8 GiB allocated to Docker**, remote model inference, one parser attempt, and **100–200 small text-native documents capped at approximately 1,000–2,000 chunks total**.

Exclude optical character recognition (OCR), scanned or large PDFs, and local language models. Start with small files and explicit parser, input, and spool limits. The two-shard correctness fixture can still be tiny.

Keep authentication, parser isolation, private storage, and exact permission filtering. Reduce corpus size or concurrency rather than removing these boundaries.

If the full service set cannot fit, report that outcome and require a larger Docker allocation or host. This trial neither qualifies the 25,000-document workload nor replaces the 64 GiB benchmark. Publish measured requirements only after the relevant workload passes.

## Consequences

### Positive

- **Exact revisions can share unchanged vectors.** Logical membership stays authoritative in PostgreSQL, so a new revision does not rewrite surviving Chroma records or duplicate the whole corpus.
- **Routine retries preserve history and healthy serving.** Frozen payloads and never-reused generation IDs make identical insert retries understandable without requiring a routine restart of healthy releases.
- **Ownership remains explicit.** The application selects current authorized scope and verifies readiness; Chroma stores derived search records. Release changes, permission changes, and physical writes do not become competing authorities.

### Negative

- **The design retains real coordination state.** Immutable generations, manifests, frozen temporary payloads, attempt evidence, readiness, and tombstones must be maintained even though the vectors themselves do not change.
- **Avoiding vector rewrites does not remove corpus-sized work.** Request-time authorized sets can grow as O(D), verification reads as O(N), and queries must fan out to required shards. Memory and filter limits need explicit enforcement and measurement.
- **Some failures still need intervention.** Unresolved external writes complicate final physical cleanup. Storage failure or missing published data can require maintenance or backup/restore; sharding on one host does not provide high availability.

The intended implementation remains understandable and implementable by one developer within one Indexing module. It does not require an event bus, event sourcing, a distributed lease service, or a custom search-engine compactor.

Secure backup/restore remains required for v1. Numerical reconstruction archives, automated re-sharding, distributed operation, implicit multi-profile score fusion, and a replacement for large-corpus filters remain deferred. Qualification may establish a useful, modest deployment range; it must not be presented as an already-tested million-document system.

## Alternatives considered

### Store mutable revision-membership arrays on every vector

**Withdrawn.** The previous design stored `collection_revision_ids` on each record. Adding R2 to an unchanged record replaced `[R1]` with `[R1, R2]` throughout the corpus. Retirement required another pass. Batching and sharding did not remove that O(N) write amplification.

It also introduced potentially conflicting replacements. Without a documented ordering or precondition contract, an old timed-out `[R1, R2]` replacement could arrive after `[R1, R2, R3]` and remove R3.

This was a risk inferred from the contract, not a reproduced failure or a claim that Chroma always reorders writes. The previous conservative protocol stopped serving and required old-writer/old-server quiescence before repair. A PostgreSQL lease or one successful read could not prevent the delayed Chroma mutation.

Immutable records remove that conflicting replacement from ordinary operation. The separate cleanup ambiguity remains explicit.

### Create a complete physical snapshot for every revision

**Not selected.** On the open-source backend, full snapshots would copy and index O(N) vectors for each corpus revision, even when only a small part changed.

The accepted design shares unchanged generations and gives changed numerical output separate physical identities.

### Use application-level immutable partitions

**Not selected for the initial design.** Immutable partitions reduce copying when changes are localized. They help less when changed documents are spread widely.

Under uniform independent placement, 250 random document changes touch almost all of 16 or 32 hash partitions, or about 160 of 256. Smaller partitions increase the number of collections and query fan-out.

Measure the simpler bounded generation-filter design before requiring this additional partitioning strategy.

### Use base-plus-delta segments or validity ranges

**Not selected for the initial design.** These approaches represent changes separately from a base dataset, or record when stored data is valid. They introduce additional exclusion, compaction, and ordering machinery.

That machinery is not required before measuring the accepted bounded-filter design. A failed qualification target should trigger an explicit decision about scope or the adapter, not silently introduce a more elaborate storage system.

## References

| Reference                                                                                               | Responsibility                                                          |
| ------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| [Canonical architecture guide](../ARCHITECTURE.md)                                                      | Overall product and application architecture.                           |
| [ADR-0015: Materializations](ADR-0015-profile-specific-index-materializations-and-pipeline-bindings.md) | Profile-specific materializations and immutable pipeline bindings.      |
| [ADR-0005: Authorization](ADR-0005-api-enforced-tenancy-and-authorization.md)                           | Current permissions, group allowlists, and service-principal authority. |
| [ADR-0007: Jobs](ADR-0007-durable-jobs-idempotency-and-recovery.md)                                     | Durable jobs, recovery, and explicit safe resume.                       |
| [ADR-0013: Backup and restore](ADR-0013-minimal-hosted-observability-and-recovery.md)                   | Recovery requirements and deferred product-level reconstruction.        |
| [ADR-0014: Retention and deletion](ADR-0014-data-retention-deletion-and-external-processing.md)         | Retention, erasure, and delayed external-write cleanup.                 |

The Chroma documentation, release, and source references are retained beside the corresponding retry and recorded-evidence sections.
