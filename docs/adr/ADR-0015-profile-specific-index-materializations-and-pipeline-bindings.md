# ADR-0015: Profile-specific generations, materializations, and pipeline bindings

**Status:** Accepted — v1 design; implementation and performance qualification pending.
**Revised:** 19 September 2026.
**Required approach:** Separate source ingestion, exact collection membership, immutable profile-specific vector generations, and ready pipeline bindings.
**Source:** [Canonical architecture guide](../ARCHITECTURE.md).
**Related:** [Lineage](ADR-0003-immutable-rag-lineage-and-release-identities.md), [vector protocol](ADR-0004-postgresql-source-of-truth-and-shared-chroma.md), [authorization](ADR-0005-api-enforced-tenancy-and-authorization.md), [model gateway](ADR-0006-byok-provider-boundary.md), [durable jobs](ADR-0007-durable-jobs-idempotency-and-recovery.md), [releases](ADR-0009-sticky-logical-canary-deployments.md), [processing](ADR-0016-docling-processing-and-cross-encoder-reranking.md).

## Context

Inframeld turns source documents into searchable evidence for a **retrieval-augmented generation (RAG)** pipeline. The pipeline retrieves document excerpts and supplies them to a model to help generate an answer.

The same document can be processed in different ways, embedded using different models, and included in several collections or pipeline versions. Those changes do not all require the same work. Editing a prompt should not recreate unchanged vectors. Choosing another processing profile should not require uploading the same source bytes again.

From first principles, **accepting a source, choosing collection members, preparing searchable data, and selecting that data for a pipeline are separate operations**. Keeping them separate lets the application reuse compatible work while recording exactly what each version uses.

It also makes readiness meaningful. A collection can exist before its index is complete, and a pipeline build can have an ID before it is ready to serve. Neither should appear usable merely because its initial records exist.

## Decision

**Admit source documents independently of their processing and embedding choices. Prepare immutable, reusable physical vector generations; verify exact collection/profile combinations as materializations; and bind each immutable pipeline version only to complete, compatible, ready materializations.**

For v1, each pipeline uses **one processing profile and one embedding profile**. It can select multiple logical collections, provided their bindings are compatible and their combined query scope fits the qualified limits.

PostgreSQL owns exact revision membership and the generation references used to filter searches. Chroma stores the derived numerical records. Mutable Chroma revision arrays and routine server restarts after candidate-write timeouts are superseded by [ADR-0004](ADR-0004-postgresql-source-of-truth-and-shared-chroma.md).

This design is accepted. **Qualification means testing its implementation and performance; it is not a claim that those tests have already passed.**

### 1. Distinguish sources, processing results, indexes, and bindings

A **DocumentVersion** identifies an immutable version of a source’s content. A **logical collection** groups document versions; a **collection revision** records its exact membership. The collection does not own a private copy of every vector used to search its documents.

A **chunk** is an excerpt produced by processing a document. An **embedding** is a numerical vector representing text for similarity search.

| Concept                            | Responsibility                                                                                                                                                                                                                                            |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`ProcessingProfile`**            | Immutable parser/chunker behavior: how the source is read and divided into chunks.                                                                                                                                                                        |
| **`ProcessingGeneration`**         | The resulting chunk evidence for a document version processed under that profile.                                                                                                                                                                         |
| **`EmbeddingProfile`**             | Immutable vector-space configuration: semantic gateway routing, model, dimensions, normalization, and distance metric. Dimensions specify the number of values in a vector; normalization and the metric determine how vectors are prepared and compared. |
| **`VectorGeneration`**             | One immutable physical numerical execution for a document processing generation and embedding profile. It owns its record IDs and frozen manifest evidence. A manifest is an inventory of expected records, identities, and verification information.     |
| **`VectorIndex`**                  | The application’s profile-specific search resource. It is not necessarily one physical Chroma collection.                                                                                                                                                 |
| **`VectorLayout` / `VectorShard`** | The immutable placement contract and the physical shard references. A shard is a partition of the index; the layout records how records are placed.                                                                                                       |
| **`IndexMaterialization`**         | A verified binding of one collection revision and profile combination to exact physical generations in one layout. It identifies the searchable data required for that revision.                                                                          |
| **`PipelineIndexBinding`**         | An immutable reference from a pipeline version to a ready materialization. It selects existing verified index data rather than copying it into the pipeline.                                                                                              |

#### Keep ownership with the responsible module

**Indexing** owns processing profiles/generations, chunks, vector generations, layouts, and materialization readiness. Its processing submodule performs source-to-chunk work; it does not become a second owner of materializations.

**Pipelines** owns pipeline versions and their bindings. Application use cases coordinate these owners without duplicating their state or rules.

These are bounded business areas in the modular application, not separate services. Domain rules enforce compatibility and lifecycle policy without importing Chroma, SQLAlchemy, or Docling. SQLAlchemy is a database library; Docling is the document-processing implementation. Their adapters implement infrastructure behavior outside the domain.

Lightweight **CQRS**, or _Command Query Responsibility Segregation_, lets status queries assemble useful read views without rebuilding the objects used for state changes. Displaying status must not construct a corpus-sized aggregate: an object containing every related document or chunk. A **corpus** is the selected body of documents.

Organization and project identities are mandatory ownership scope. They do not require cross-organization sharing or an enterprise organization-management interface in v1. Authentication and document-group policy remain application authorization under ADR-0005, regardless of the identity provider.

### 2. Admit sources once and prepare additional profiles on demand

Users upload or synchronize documents without choosing an embedding profile for every file. A connector admits a source once; that source can later be processed under several immutable processing profiles and embedded under several model profiles.

The project/build selects the profiles. The application creates the document version, reuses or produces its compatible processing generation, and schedules vectorization only when required. **Vectorization** is the work of producing numerical embeddings for the processed chunks.

Creating a profile records it in PostgreSQL and queues asynchronous provisioning. **Provisioning** prepares the required infrastructure/configuration for later use. It does not create Chroma state inside the profile-creation transaction and does not immediately re-embed the whole project.

| Change                                                                                                   | Required behavior                                                                                                                                                      |
| -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Create an additional profile**                                                                         | Record and provision it asynchronously. Index data under it on demand, rather than silently multiplying model cost and memory use.                                     |
| **Change the embedding model, dimensions, normalization, distance metric, or semantic gateway behavior** | Create a new immutable embedding profile. Semantic behavior means what vectors the configured connection/model produces, not merely which credential permits the call. |
| **Rotate a credential without changing semantics**                                                       | Do not create a new embedding profile solely because the secret changed.                                                                                               |
| **Change the processing profile**                                                                        | Produce new chunks and embeddings where required, reusing the original unchanged source bytes rather than requiring another upload.                                    |
| **Change only the prompt with the same collection revision and profiles**                                | Reuse the ready materialization.                                                                                                                                       |

The interface must distinguish source ingestion, processing, profile provisioning/vectorization, logical revision state, and materialization status. They are not one undifferentiated “ready” flag.

Users choose from supported processing profiles. Arbitrary parser/chunker plugins remain deferred behind the existing processing ports. A **port** is an application-owned interface for a capability; preserving it does not require implementing a plugin system now.

### 3. Keep the reuse key separate from physical vector identity

The **semantic reuse key** identifies compatible work:

```text
organization/project
    + document version
    + processing generation
    + embedding profile
```

PostgreSQL resolves that key to a healthy, ready physical generation or its already-admitted build. **Admission** means durably accepting the work, so another request can refer to the existing operation rather than treating it as unknown.

A physical generation has a separate, never-reused **incarnation ID** identifying one numerical execution. Every physical record ID includes that incarnation together with its chunk identity.

**Compatible inputs allow reuse of existing output; they do not permit overwriting that output with a fresh model response.**

| Operation                                                   | Identity rule                                                                                                                                       |
| ----------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Reuse compatible ready output**                           | Select the existing physical generation.                                                                                                            |
| **Retry a captured write**                                  | Use the same sealed payload and physical record IDs. A sealed payload is the exact write data saved before dispatch and kept unchanged for retries. |
| **Execute the model again and obtain new numerical output** | Use a fresh physical generation identity and corresponding record IDs. Never overwrite retained records under the semantic reuse key.               |

A logical revision, prompt change, or pipeline ID is not part of vector identity. This is what lets compatible revisions and pipeline versions share existing numerical records.

### 4. Verify a materialization before publishing its readiness

A materialization is identified by this combination:

```text
collection_revision_id
    + processing_profile_revision_id
    + embedding_profile_id
    + vector_index_id
    + layout_id
```

Its normal lifecycle is:

```text
requested -> indexing -> ready
                      -> failed

ready -> stale, when a verified dependency becomes unavailable or invalid
```

A failed or unfinished materialization is not partially ready. An exhausted transient-retry budget leaves a failed job with its existing identity and an exhausted-budget reason. Explicit safe resume follows [ADR-0007](ADR-0007-durable-jobs-idempotency-and-recovery.md).

#### Record and verify the exact expected data

Each materialization records exact generation references, expected and verified immutable manifest hashes, counts, and per-shard progress.

Verification has two related responsibilities:

| What is being verified?              | Required evidence                                                                                                                                                                      |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A new physical vector generation** | Check the actual numerical records against their frozen payload. An expected hash copied into record metadata is not proof that the stored vector matches.                             |
| **A new materialization**            | Initially read all expected IDs, immutable metadata, and placement in bounded pages. Reuse already-verified numerical-generation evidence and perform targeted checks of actual bytes. |

A **bounded page** limits the amount read at once. It avoids loading the entire inventory into memory without skipping required verification.

After verification, a final conditional PostgreSQL transaction checks job ownership, lifecycle, and dependencies before publishing readiness. A conditional transaction commits that state change only when its required conditions still hold.

No mutable membership projection is written to Chroma. Ready shared generations keep their values when other revisions are admitted or retired. ADR-0004 supplies the exact write/retry protocol and qualification gates; this ADR adds neither another vector writer nor a weaker verification rule.

#### Full verification still has a cost

Let **D** be the number of document-version memberships and **N** the number of chunks. Source/membership manifest assembly can require **O(D)** work, and verification can require **O(N)** record reads: the work grows with those counts.

**Avoiding writes to unchanged vectors does not make the entire build proportional only to the changed documents.** Bounded pages limit memory per step, not total verification work.

### 5. Worked example: change a prompt, then change one document

Start with pipeline **v1**, collection revision **A**, and prompt **P1**. Its materialization is complete and ready.

| Version | Change                                                          | Indexing behavior                                                                                                                 |
| ------- | --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **v1**  | Revision A with prompt P1.                                      | Uses A’s ready materialization under the selected profiles.                                                                       |
| **v2**  | Keep revision A and the same profiles; change the prompt to P2. | Reuses A’s materialization. No new embeddings are needed for this prompt-only change.                                             |
| **v3**  | Change one source document and select the resulting revision B. | Reuses unchanged ready generations and prepares the changed document’s chunks and vectors, then verifies B’s full expected scope. |

For v3, the durable build freezes revision B, its profiles, and its requested configuration. Later edits do not change those inputs while the build runs.

The build reuses all unchanged ready generations, inserts only the new document version’s chunks, verifies B’s complete expected scope, and publishes B’s materialization as ready. The complete immutable **v3 and its bindings are published only when every required materialization is ready**.

A reserved pending version ID is not a pipeline that can serve requests. Building B and subsequently promoting v3 do not update A’s vector records. Promotion changes the serving selection through Releases; it is not another indexing write.

[ADR-0004](ADR-0004-postgresql-source-of-truth-and-shared-chroma.md) expands this example with two chunks per document, two physical shards, exact query filters, and retention behavior.

### 6. Separate historical readiness, current health, and candidate retries

A ready materialization records that its build passed verification. It does not prove that storage will remain healthy forever.

| Situation                                                              | Required behavior                                                                                                           |
| ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **Backend outage, missing published records, or integrity conflict**   | Make the affected dependencies unavailable. Historical readiness does not authorize serving from damaged or missing data.   |
| **An unrelated candidate’s immutable insert has an uncertain outcome** | Keep healthy existing generations available. Do not mark the entire healthy index unavailable or force a Chroma restart.    |
| **Safe candidate-write retry**                                         | Retry the same frozen IDs and bytes within the configured budget. Current release A can continue while candidate B retries. |
| **Retry budget exhausted**                                             | Fail B’s job visibly, retaining its identity and exhausted-budget reason. An explicit safe resume follows ADR-0007.         |
| **Published numerical data is missing**                                | Use backup/restore or intervention. Do not silently reconstruct the index by calling the embedding model again.             |

An uncertain insert means its response did not establish whether Chroma completed it. Because the payload is immutable, any earlier accepted insert and its safe retry carry the same generation data.

PostgreSQL checks current ownership before publication. A superseded attempt cannot publish merely because it later finishes, including after a replacement worker has taken over. That database ownership check does not cancel the earlier external request.

#### Recheck health while a query executes

A request pins its selected dependencies and records their **health generation**, a revision used to detect a change in dependency health. Recheck it before content egress and result release, along with the retrieval checks below. **Egress** means sending content out to a processing component or caller.

A query must not release a result on the strength of an earlier healthy check when the selected dependency has since become unavailable or invalid.

Temporary unfinished-write payloads in SeaweedFS are retry evidence, not a complete archive of published vectors. Product-level reconstruction and retained numerical archives remain deferred. Reclaiming a temporary payload must not discard unresolved external-attempt cleanup evidence.

### 7. Bind each pipeline to an exact, compatible retrieval configuration

An immutable pipeline version records one processing profile, one embedding profile, exact collection revisions, and matching ready materializations. It also records retrieval, prompt, and generation configuration and a complete configuration fingerprint.

A **fingerprint** identifies the recorded configuration for comparison and verification. It does not replace the configuration or its required artifacts.

All bindings must have compatible profile and layout identities. A missing, stale, failed, retired, or incomplete required dependency prevents serving.

Deployment commands recheck dependencies and the expected Deployment revision. A **Deployment** selects which pipeline version serves requests; its expected revision detects a competing change to that selection. A historical ready label cannot make an unavailable rollback target valid.

#### Resolve current authorized scope before searching

The query follows this sequence:

1. **Resolve and pin the selected pipeline.** Establish which immutable version and dependencies this request will use.
2. **Compute the permitted generation set.** Combine compatible generations from the exact bound revision memberships, then intersect that set with the caller’s current project, action, and document-group access and deletion state.
3. **Build the search restriction on the server.** The vector adapter translates that scope into bounded generation `$in` filters and immutable scope/profile filters. `$in` restricts matching records to an explicit set of generation IDs.
4. **Embed the query and search every required shard.** Obtain one query embedding through `ModelGateway` for the selected profile, and send it to every required shard in that profile/layout.
5. **Merge and verify the results.** Use the same distance metric, deterministic ID ordering for ties, and overlap deduplication. Recheck result identities, current document permissions, and dependency health before text reaches a reranker, model, evaluator, or client, and before result release.

`ModelGateway` is the application-owned model-call interface. A **reranker** reorders retrieved candidates; an **evaluator** assesses pipeline results. Neither receives content outside the current authorized scope.

A fixed integration uses the groups assigned to its verified **service principal**, the application’s authenticated identity. An unverified end-user assertion cannot expand that authority.

**Zero permitted generations means no evidence and no unfiltered query.** A failed required shard makes the query unavailable; do not answer as though the remaining shards represented the complete selected corpus.

Group changes do not rewrite vector metadata. Historical revisions retain their source membership, not an old permission grant.

#### Bound the combined scope, not each collection in isolation

Across all selected logical collections, the combined query must fit the limits for generation count, serialized filter bytes, predicate count, shard fan-out, and deadline. **Predicates** are filter conditions; **fan-out** is the number of shard searches the request initiates.

Exceeding the qualified limit fails explicitly. Do not broaden the scope or introduce an unbounded loop that repeatedly splits one oversized query into smaller requests.

Exact filtering identifies the permitted corpus. It does not promise exact **approximate-nearest-neighbor (ANN)** recall or identical model answers. Recall measures how many of the true nearest results the search recovers; scope correctness and retrieval completeness are different properties.

### 8. Coordinate retention, in-flight queries, and final cleanup

**Retirement** prevents new bindings before cleanup begins. Ordinary cleanup waits for build, Deployment, retained rollback, and query references to end.

An admitted **operation pin** protects the selected artifacts while a query uses them. Pin admission shares the **retention gate** with retirement: the coordination rule that prevents cleanup and a new reader from racing past each other.

Promotion can select a new pipeline for the next query without deleting the older generation still needed by an existing query.

Release pins on terminal completion or through the enforced deadline and conclusive-termination rules in ADR-0004. Merely recording a timeout is insufficient if the old process can continue consuming data after its protection has been reclaimed.

**Explicit erasure and access revocation can override ordinary retention.** Affected operations must fail safely rather than preserve access because a historical reference exists.

#### Retired records must never become eligible again

A permanent generation **tombstone** records that a physical identity has been retired and cannot be reused. It prevents a later job from making that identity live again; it does not cancel a request already accepted by Chroma.

An unresolved old insert may finish after deletion and recreate an unreachable record. The tombstone prevents reuse and access, but physical cleanup can remain pending.

Retain the unresolved-attempt evidence even when the temporary retry payload has been reclaimed. Final-erasure **quiescence**, establishing that old writes can no longer arrive after cleanup, follows ADR-0004’s exceptional procedure. Do not confuse logical access revocation with proof that every byte has been removed.

### 9. Use the same build path during default onboarding

Default onboarding uses the ordinary frozen build/materialization path. Creating the initial collection and pipeline records does not create a version that can serve answers.

A built-in `ProcessingProfile` may exist before the user configures models or uploads documents. A valid `EmbeddingProfile`, however, requires the actual configured embedding semantics. Complete ready bindings also require verified artifacts.

```text
Default resources exist
    -> Configure actual model semantics and admit source content
        -> Ordinary frozen build and materialization verification
            -> Complete ready pipeline version
                -> Separate authorized Releases command
```

An authorized automatic-update operation invokes Releases only after readiness, for both the first default version and later updates.

Switching publication mode or superseding an update can leave a ready result unpublished. It does not transfer readiness ownership away from Indexing or extend Build’s authority to publishing customer traffic. Build publishes readiness; Releases controls serving selection.

[ADR-0019](ADR-0019-default-onboarding-and-first-publication.md) defines that onboarding and automatic-update coordination.

### 10. Build for bounded growth without claiming untested capacity

V1 uses persisted immutable layouts, deterministic placement, bounded streaming manifests/cursors, bounded write/query requests, and explicit failed-shard behavior. A **cursor** tracks a position in a larger result so it can be read in limited pages.

The same paths must work with one and two shards. No code may assume that every application index is one physical collection or that every manifest fits in memory.

The representation avoids writes to unchanged vectors. It still has **O(D)** authorized-generation/filter work and **O(N)** verification reads, along with filter-payload and query fan-out costs.

#### Provisional qualification target

| Dimension                         | Proposed test workload                                                      |
| --------------------------------- | --------------------------------------------------------------------------- |
| **Current documents**             | 25,000.                                                                     |
| **Current chunks**                | Approximately 500,000.                                                      |
| **Profile scope**                 | One profile, within the one-processing/one-embedding-profile pipeline rule. |
| **Retained collection revisions** | Three.                                                                      |
| **Physical shards**               | Two.                                                                        |
| **Concurrent requests**           | Five.                                                                       |
| **Proposed host**                 | 64 GiB RAM and 16 vCPUs.                                                    |

These are **qualification targets, not performance guarantees**. ADR-0004 defines the calculations, benchmark phases, tentative numerical goals, and criteria for stopping or reconsidering the design. Its separate modest local trial is not a production-capacity benchmark.

#### Defer additional storage machinery until measurements justify it

Automatic re-sharding, multiple writer hosts, distributed Chroma management, segment compaction, and a different large-corpus membership representation are deferred. Re-sharding changes physical partitioning; segment compaction reorganizes stored segments. Neither is added merely to avoid measuring the current design.

Chroma Cloud can provide a future adapter/deployment, but OSS correctness and release history do not depend on Cloud-only collection forks. **OSS** means the open-source product; a collection fork is a backend facility for creating a related collection without treating it as an ordinary full copy.

Preserve port, layout, and generation identities, while recognizing that a later data migration may still require substantial work.

#### Do not implicitly combine profiles in one query

Multi-profile retrieval is deferred. It would require one query embedding per profile, explicit **score fusion** to combine results from different vector spaces, separate readiness/evidence, and a versioned contract for partial failures.

A collection may have several profile-specific materializations available. **Their existence does not authorize a pipeline query to mix them.**

### 11. Verify reuse, publication, retrieval, and cleanup together

These are implementation acceptance requirements, not completed test results.

| Area                                  | Required verification                                                                                                                                                                                   |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Source/profile independence**       | Admit a source once and reuse it across compatible processing/embedding work. Provision profiles asynchronously without requiring the corpus to be uploaded again.                                      |
| **Binding compatibility**             | Reject incompatible profiles/layouts. A pipeline cannot serve while any required shard or materialization is incomplete.                                                                                |
| **Reuse without historical mutation** | Prompt-only changes reuse ready materializations. Membership-only changes write zero surviving vector records and leave historical hashes unchanged.                                                    |
| **Physical identity**                 | Record IDs include the execution incarnation. A new numerical response never overwrites retained records under an existing semantic reuse key.                                                          |
| **Retry and publication**             | Lost insert responses and worker crashes retry frozen bytes within budgets, preserve healthy current serving, and cannot publish stale-attempt or partial candidates.                                   |
| **Authorized retrieval**              | Generation filters combine exact membership with current permissions. Forged identities, empty scopes, and revoked groups cannot broaden retrieval or evidence access.                                  |
| **Retention and erasure**             | Query pins prevent ordinary garbage-collection races. Tombstoned generations never become live again, and unresolved late writes remain visibly pending physical cleanup.                               |
| **Shards and measured limits**        | Exercise the same paths with one- and two-shard fixtures. Fail required-shard errors explicitly, and pass complete lifecycle, resource, and recall tests before publishing a supported operating range. |

These responsibilities belong inside the modular application. Separate lifecycle states, asynchronous work, temporary retry storage, and cleanup evidence are not a reason to introduce an event bus, event sourcing, or a second search engine prematurely.

## Consequences

### Positive

- **Sources and compatible numerical work are reusable.** Users do not re-upload unchanged documents for another profile, and prompt or membership changes do not rewrite surviving vectors.
- **A pipeline’s retrieval inputs are explicit.** Exact revisions, profiles, layouts, physical generations, and verified bindings describe what it uses without following mutable “latest” values or copying every vector per pipeline.
- **Readiness, current access, and release selection stay separate.** Healthy releases can continue while candidates retry, historical references do not preserve revoked permissions, and default onboarding uses the same verification rules as later builds.

### Negative

- **The application must manage several related lifecycles.** Source admission, processing, provisioning, vectorization, materialization readiness, and pipeline binding need distinct state and visible progress.
- **Reuse does not eliminate corpus-sized work.** Authorized-generation queries and filters can grow with document membership; verification can read all expected chunks. Fan-out, filter sizes, memory, and latency must be bounded and measured.
- **Immutable storage still needs recovery and cleanup protocols.** Temporary frozen payloads, attempt ownership, query pins, and tombstones must be maintained. Missing published data can require restore/intervention, and unresolved late writes can delay final physical cleanup.

## Alternatives considered

The following approaches are excluded, superseded, or deferred by this decision. No separate comparative assessment is recorded.

### Couple each upload to one embedding profile

**Not selected.** Source admission is independent of processing and embedding selections. The same source can support several profiles on demand, without repeated uploads or immediate re-embedding of the whole project whenever a profile is created.

### Store private vectors or mutable revision membership for every collection

**Not selected.** Logical collections share compatible immutable physical generations. PostgreSQL owns exact membership; adding or retiring a revision does not rewrite membership arrays on Chroma records. ADR-0004 supersedes the mutable-array protocol.

### Reuse a physical record ID for a fresh numerical execution

**Ruled out.** The semantic key identifies compatibility for reuse. A new numerical execution requires a distinct physical incarnation, while safe write retries use the exact captured bytes under the original IDs.

### Restart healthy Chroma after an uncertain candidate insert

**Superseded as the ordinary retry approach.** Retry and verify frozen IDs/bytes within bounds while healthy current generations continue serving. Missing published data and exceptional final cleanup remain separate cases that may require intervention.

### Mix profiles implicitly or add distributed indexing infrastructure now

**Deferred.** V1 deliberately keeps one processing and one embedding profile per pipeline, a persisted layout, bounded operations, and tested one-/two-shard paths. Multi-profile score fusion, automatic re-sharding, multiple writer hosts, distributed management, compaction, and a replacement large-corpus representation require measured need and their own explicit behavior.

## References

| Reference                                                                             | Responsibility                                                                                                  |
| ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| [Canonical architecture guide](../ARCHITECTURE.md)                                    | Overall product architecture and the relationship between ingestion, indexing, pipelines, and serving.          |
| [ADR-0003: Lineage](ADR-0003-immutable-rag-lineage-and-release-identities.md)         | Immutable source/configuration lineage and separate physical numerical identities.                              |
| [ADR-0004: Vector protocol](ADR-0004-postgresql-source-of-truth-and-shared-chroma.md) | Exact writes/retries, verification, layouts, query filters, retention gates, cleanup, and qualification limits. |
| [ADR-0005: Authorization](ADR-0005-api-enforced-tenancy-and-authorization.md)         | Current application permissions, document groups, and fixed integration authority.                              |
| [ADR-0006: Model gateway](ADR-0006-byok-provider-boundary.md)                         | Model-call routing and the distinction between semantic configuration and credentials.                          |
| [ADR-0007: Durable jobs](ADR-0007-durable-jobs-idempotency-and-recovery.md)           | Job identity, bounded retries, ownership, failure, and explicit safe resume.                                    |
| [ADR-0009: Releases](ADR-0009-sticky-logical-canary-deployments.md)                   | Serving transitions, expected Deployment revisions, and rollback availability.                                  |
| [ADR-0016: Processing](ADR-0016-docling-processing-and-cross-encoder-reranking.md)    | Supported processing profiles, source-to-chunk work, and reranking.                                             |
| [ADR-0019: Default onboarding](ADR-0019-default-onboarding-and-first-publication.md)  | Default setup and authorized automatic-update callers of the ordinary build/release operations.                 |
