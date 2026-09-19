# ADR-0003: Immutable RAG lineage and mutable release/security state

**Status:** Accepted — lineage foundation; implementation qualification pending.  
**Revised:** 19 September 2026.  
**Required approach:** Immutable lineage, with release selections and current security decisions managed separately.  
**Related:** [Indexes](ADR-0004-postgresql-source-of-truth-and-shared-chroma.md), [release transitions](ADR-0009-sticky-logical-canary-deployments.md), [materializations](ADR-0015-profile-specific-index-materializations-and-pipeline-bindings.md).

## Context

Inframeld uses **retrieval-augmented generation (RAG)**: it retrieves relevant document excerpts and supplies them to a language model to help answer a question. The result depends on the document content, how that content was processed and indexed, and the pipeline configuration used for the request.

Those inputs can change independently. A document can be updated without changing a prompt. A prompt can change without requiring new embeddings. An engineer can promote a new version, and a user's access can be revoked after an answer was produced.

The starting point is to separate three questions:

| Question                                            | What answers it                                                                                                  |
| --------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **What produced this answer or evaluation result?** | Recorded source versions, configuration, artifacts, and execution details. Together, these form its **lineage**. |
| **Which version should serve requests now?**        | The Deployment's current release state.                                                                          |
| **Who may read this content now?**                  | Current permissions, including permissions on historical content.                                                |

We need to preserve the first without freezing the other two. Otherwise, updating a release could change the apparent origin of an old answer, or an old access decision could continue exposing content after permission was revoked.

## Decision

**Use distinct identities for things with different lifecycles. Preserve historical inputs and evidence, while allowing release selections, availability, and permissions to reflect current state.**

An **immutable** record keeps the same meaning under the same identity. Changing its content or configuration requires a new version or generation rather than rewriting the old one.

Immutability does **not** mean that the underlying bytes are retained forever, that dependencies cannot fail, or that historical permissions remain valid.

### 1. Separate a document's identity from its content and processing results

The source and processing relationships are:

```text
Document -> immutable DocumentVersion
DocumentVersion + ProcessingProfile -> ProcessingGeneration + chunk manifest
```

A **Document** identifies a logical source. A **DocumentVersion** identifies a particular version of its content.

For the same Document, observing an unchanged authoritative content hash is **idempotent**: repeating the observation does not create a duplicate version. Changed bytes create a new immutable DocumentVersion instead of replacing the old content.

A **ProcessingProfile** specifies how content is processed. A **ProcessingGeneration** records the resulting processed content and chunks. A **chunk** is an excerpt prepared for retrieval, and its **manifest** records the chunks produced by that generation.

A processing generation is reusable only when both the source version and the complete **processing fingerprint** match. The fingerprint identifies everything that can affect the processing output: the implementation, model and tokenizer revisions, and the output-affecting configuration. A tokenizer is the component that splits text into the units used by a model or processing step.

Matching a profile's name is not enough if those underlying inputs changed.

**Chunk IDs are scoped to their ProcessingGeneration.** A chunk's identity must be understood together with the generation that produced it.

### 2. Separate reusable embedding inputs from the actual numerical output

An **embedding** represents text as a numerical vector for similarity search. An **EmbeddingProfile** identifies the embedding behavior and configuration used to produce those vectors.

Two identities serve different purposes:

```text
ProcessingGeneration + EmbeddingProfile -> semantic Vectorization reuse key
Vectorization -> immutable physical VectorGeneration + numerical payload evidence
```

| Identity             | What it identifies                                                                                                                                                                                              |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Vectorization**    | The semantic inputs used to decide whether existing embedding work is compatible and reusable. Its reuse key includes the organization/project, document version, processing generation, and embedding profile. |
| **VectorGeneration** | One physical numerical execution of those inputs: the particular generated vectors and the evidence of their numerical payload.                                                                                 |

This distinction matters because **matching inputs do not authorize overwriting existing numerical output**.

A compatible build can reuse a ready physical VectorGeneration. However, running the embedding computation again creates a fresh physical generation, even when its semantic inputs match a previous execution. Retained records from the earlier generation must not be overwritten.

Each physical vector record ID includes its immutable vector generation, or **incarnation**, and chunk ID within the fixed profile/layout namespace. The namespace is the storage scope for that profile and layout; the layout describes the physical arrangement of the index.

In other words, a fresh numerical execution gets a distinguishable physical identity. Reusing existing output and producing new output are different operations.

### 3. Bind collections and pipeline versions to exact indexed inputs

The collection and pipeline relationships are:

```text
CollectionRevision -> exact DocumentVersion memberships
CollectionRevision + ProcessingProfile + EmbeddingProfile -> IndexMaterialization
PipelineVersion -> immutable configuration + ready materialization bindings
```

A **CollectionRevision** records exactly which document versions belong to a collection. It must never resolve its contents through a mutable reference such as “latest.”

An **IndexMaterialization** connects that exact collection revision and its processing/embedding profiles to the physical index generations needed to search it.

A **PipelineVersion** has immutable configuration and bindings to one or more compatible materializations. It references **one processing profile, one embedding profile, and an optional configured reranker**. A reranker reorders retrieved candidates before the final context is selected.

Source changes do not alter an existing collection revision or pipeline version. A new source version is a different input, not a replacement hidden behind the old identity.

A prompt, retrieval, or reranker change can reuse existing embeddings when their vector semantics remain unchanged. **A configuration change does not automatically mean the documents must be embedded again.**

#### PostgreSQL owns membership; Chroma stores physical search records

PostgreSQL and manifests bind exact collection revisions to physical vector generations. A manifest is a recorded description of the artifacts or memberships involved.

Pipeline and collection IDs are not embedded in every vector. The accepted Chroma design has **no mutable `collection_revision_ids` projection**: it does not maintain an editable list of logical collection revisions on each shared vector record.

Physical Chroma collection names remain infrastructure references, not the business identities of Inframeld collections or pipeline versions.

#### Credential rotation is not a semantic model change

Rotating a credential changes the application's ability to call a service. It does not, by itself, create a new semantic model revision.

Changing what an endpoint or model **means or does** is different and requires new lineage. A credential update must not be confused with a change to the model behavior described by the recorded configuration.

### 4. Check present availability before serving a historical version

A materialization is usable only after its required data and shards have been verified. A **shard** is a physical portion of the index that the materialization needs.

Pipeline creation validates its materialization bindings. Deployment transitions must reference versions that can actually serve requests.

**“This version was successfully built” and “this version can be served now” are different facts.**

The evidence of a completed build remains immutable, but damage or explicit erasure can make its dependencies unavailable. The system must report that condition rather than treat historical success as proof of present readiness.

#### Release changes move pointers, not history

```text
Deployment -> mutable current/candidate/previous pointers
```

A **Deployment** selects the pipeline versions used for serving. Its **current**, **candidate**, and **previous** pointers identify the live version, a version being tried, and a previous release target.

Promotion, candidate rejection, and rollback change those pointers according to [ADR-0009](ADR-0009-sticky-logical-canary-deployments.md). They do not rewrite an answer already produced.

A query selects **one PipelineVersion for its entire execution** and records which variant it used. A release change must not make a single query switch configurations halfway through.

Citations are established through backend-owned source IDs and **source spans**, which identify locations within source content. A model cannot invent valid source identities or citation locations.

### 5. Apply current permissions to historical content

**An immutable collection membership is not an immutable permission grant.**

Removing a user's document access must also protect that document's old versions, citations, and evaluation evidence. Keeping historical hashes or configuration records does not keep the user authorized to read their content.

Record the access context and revision used when an operation executes. That record explains the execution; it does not replace permission checks on later reads or before sensitive results are released.

The query path resolves **current authorized generation membership before vector search**. It determines which generations belong to the selected inputs and which of those the caller may currently access. The runtime cost of this resolution still needs qualification.

#### Initial access model

The initial design uses **group allowlists** and **fixed integration authority** under ADR-0005. A group allowlist identifies groups permitted to access the relevant documents. Fixed integration authority means an application integration uses its own configured permissions, not permissions claimed by an arbitrary end-user identifier.

The access context distinguishes the verified **actor**, which is the authenticated caller, from an optional **delegated subject**, which would identify a user the actor is verified to represent.

Fine-grained access-control lists (ACLs) and verified delegation are deferred. An unverified subject must never grant access.

A **canary affinity key** is an opaque routing value used to keep requests in a consistent rollout group. It is not proof of end-user identity and cannot grant that user's permissions.

### 6. Preserve the exact inputs of each evaluation

Engineers maintain a pipeline's tests and inspect evaluation history inside Inframeld.

```text
Pipeline benchmark -> stable case identities + immutable case-content snapshot
EvaluationRun -> benchmark snapshot + PipelineVersion + evaluator revision + access context
```

A **benchmark** is the set of test cases used to evaluate a pipeline. Each case has a stable identity, while a run binds to an immutable snapshot of the exact questions and labels used at execution.

An **EvaluationRun** also records the exact PipelineVersion, evaluator revision/settings, and access context used for that run.

Editing a question creates new evaluation inputs. Changing the **groundedness rubric**—the rules used to judge whether an answer is supported by its supplied context—also creates new evaluation inputs. Neither action rewrites old case results or changes the PipelineVersion.

ADR-0008 defines the minimal snapshot and comparison model.

Adding a future evaluation-platform adapter and replacing a metric are separate changes. Neither gives the evaluation system ownership of serving release pointers.

### 7. Attach feedback to the answer that was actually served

The existing **AnswerReceipt** records the provenance of a served answer: the information that identifies what actually produced it.

At **query admission**, when the application accepts the query for execution, the receipt records the selected pipeline version, deployment revision, and rollout/cohort. It subsequently records the completion outcome. A cohort is the routing group to which the request belongs.

The receipt must identify **every source used in the final generation context, not only the sources cited in the answer**. A source can influence an answer without appearing in its citations; its identity is still needed for current access checks.

Feedback references that receipt. A later promotion or rollback cannot attribute the feedback to whichever version happens to be current when it arrives.

The current rating may change, but that does not rewrite the answer's immutable serving provenance, its PipelineVersion identity, or offline EvaluationRun evidence.

[ADR-0017](ADR-0017-answer-feedback.md) defines the accepted record, API, and retention behavior. The receipt records provenance and outcome without storing the full production answer.

### 8. Define reproducibility without promising identical execution

Lineage explains **which inputs, configuration, and artifacts were used**. It does not promise that executing them again will produce exactly the same result.

In particular, this decision does not guarantee byte-identical output from a hosted large language model (LLM), unchanged behavior behind a model alias that an external provider has changed, or identical result ordering after rebuilding an approximate-nearest-neighbor index. That index performs approximate similarity search over vectors.

**IDs and hashes alone cannot reconstruct numerical embeddings.** Knowing which inputs were used is not the same as retaining the actual numerical output.

| Capability                          | Treatment in this decision                                                                          |
| ----------------------------------- | --------------------------------------------------------------------------------------------------- |
| **Lineage records**                 | Preserve the identities and relationships needed to explain an execution.                           |
| **Normal immutable-write recovery** | Accepted for qualification under ADR-0004. This is distinct from reconstructing lost product state. |
| **Tested backup and restore**       | Remain the recovery baseline under ADR-0013.                                                        |
| **Product-level reconstruction**    | Deferred. Lineage is not a promise that Inframeld can rebuild every lost artifact.                  |
| **Permanent numerical archives**    | Deferred. Immutable physical generations do not imply permanent retention of every vector payload.  |

The immutable physical-generation design, PostgreSQL-owned membership, and initial group/fixed-integration permissions are accepted. **Implementation qualification is still pending**: the implementation must be tested against the design, including the runtime cost of resolving authorized generation membership. Acceptance is not a claim that this testing has already passed.

### 9. Examples of the resulting behavior

| Change or event                                            | Expected behavior                                                                                   |
| ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| **Release prompt B against the same corpus and profiles.** | Reuse the compatible ready materialization; the prompt change does not require new embeddings.      |
| **Change the embedding model.**                            | Create lineage for the new vector space rather than overwrite the old numerical generations.        |
| **Revoke Alice's document access.**                        | Deny her historical source reads too, even though the historical hashes remain recorded.            |
| **Delete source data needed by an older release.**         | The rollback target may become unavailable. Report that fact rather than fabricate reproducibility. |

These relationships describe product behavior. They are not separate services, and they do not require an object-relational mapping (ORM) aggregate for every manifest entry.

## Consequences

### Positive

- **Changes remain explainable.** Source versions, pipeline configuration, evaluations, and answer receipts retain their original identities and relationships rather than following later edits.
- **Compatible work can be reused without rewriting history.** Prompt, retrieval, and reranker changes can reuse ready materializations when vector semantics are unchanged. Fresh numerical executions cannot overwrite retained generations.
- **Release and security changes remain independent of historical evidence.** Moving a Deployment pointer does not reattribute an answer, and retaining an old version does not preserve a revoked permission.

### Negative

- **More relationships must be recorded and maintained.** Documents, processing results, numerical generations, collection memberships, bindings, evaluations, and receipts cannot be collapsed into one mutable record.
- **Authorization remains work performed at read time.** Historical records do not eliminate current permission checks. Resolving permitted generations before vector search has a runtime cost that still needs qualification.
- **Historical availability and exact reproduction are not guaranteed.** Damage or erasure can remove a rollback target or required evidence. Lineage is not a substitute for backup/restore or a permanent numerical archive.

## Alternatives considered

No separate comparative evaluation is recorded. The approaches below are excluded or deferred by this decision.

### Let historical versions follow the latest source content

**Ruled out.** A collection revision contains exact DocumentVersions, and a PipelineVersion binds to exact compatible materializations. Following “latest” would change a version's effective inputs without changing its identity.

### Use semantic reuse keys as overwriteable physical vector identities

**Ruled out.** Matching inputs establish compatibility for reuse, not permission to replace previously recorded numerical output. A fresh numerical execution receives a distinct immutable physical generation.

### Keep mutable collection-revision membership on Chroma records

**Not selected.** PostgreSQL and manifests bind exact revisions to physical generations. The accepted design does not maintain a mutable `collection_revision_ids` projection on shared vectors.

### Preserve historical permission decisions for historical content

**Ruled out.** An old allow decision must not survive a current revocation. Historical source reads, citations, and evaluation evidence remain subject to current access checks; an affinity key or unverified subject cannot supply missing authority.

### Treat lineage as a complete reconstruction or permanent-archive system

**Deferred and not implied by this decision.** IDs and hashes cannot recover the numerical values of embeddings. Tested backup/restore remains in scope, while product-level reconstruction and permanent numerical archives remain deferred. Ordinary immutable-write recovery is a separate capability.

## References

| Reference                                                                             | Responsibility identified by this ADR                                                      |
| ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| [ADR-0004](ADR-0004-postgresql-source-of-truth-and-shared-chroma.md)                  | PostgreSQL/Chroma ownership and normal immutable-write recovery.                           |
| ADR-0005                                                                              | Group allowlists, fixed integration authority, and the actor/delegated-subject boundary.   |
| ADR-0008                                                                              | The minimal evaluation snapshot and comparison model.                                      |
| [ADR-0009](ADR-0009-sticky-logical-canary-deployments.md)                             | Promotion, candidate rejection, and rollback transitions.                                  |
| ADR-0013                                                                              | Tested backup/restore and the deferral of reconstruction and permanent numerical archives. |
| [ADR-0015](ADR-0015-profile-specific-index-materializations-and-pipeline-bindings.md) | Profile-specific materializations and pipeline bindings.                                   |
| [ADR-0017](ADR-0017-answer-feedback.md)                                               | Answer receipts, feedback, API behavior, and retention.                                    |
