# Profiles, generations and verified preparation

<a id="profiles-generations-and-verified-preparation"></a>

Alice changes chunking while keeping the same handbook bytes. She needs another preparation result, not another upload. A prompt-only change may instead reuse an existing ready materialization. Indexing distinguishes source identity, requested meaning and actual numerical execution.

<a id="the-records-solve-different-problems"></a>

## Apply accepted PD-INDEXING-05

Accepted [PD-INDEXING-05](decision-parser-runtime-profile.md#approved-resolution) selects this workflow's detailed contract. A small uploaded file can expand into huge content or spawn children. File size alone cannot protect the host or isolate the next document. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## Choose a focused reading task

- For complete readiness verification, read [Materialization verification](materialization-verification.md).

## The records solve different problems

| Concept | What it fixes |
| --- | --- |
| ProcessingProfile | Parser/chunker settings and required assets. |
| ProcessingGeneration | Actual processing output for one DocumentVersion. |
| Chunk | Processed text with source/artifact coordinates. |
| EmbeddingProfile | Numerical meaning, model and complete embedding configuration. |
| Vectorization | Semantic reuse key for the requested vector work. |
| VectorGeneration | One actual numerical execution with its own identities. |
| VectorIndex | Saved layout of physical Chroma collections or shards. |
| IndexMaterialization | Verified exact revision/profile/generation bindings. |

These distinctions do not mandate an aggregate or repository per concept. PostgreSQL owns membership and current policy. Chroma must not contain mutable corpus-membership arrays, group lists or serving flags.

<a id="prepare-exact-inputs"></a>

## Prepare exact inputs

1. Capture the complete authorized corpus and profiles. A direct query or evaluation can prepare a working-configuration snapshot without creating a PipelineVersion. It must not mutate live vector generations.
2. Reuse exact compatible generations or perform ordinary new processing and gateway-controlled embeddings. Parsing remains offline in the per-attempt sandbox with pinned assets and validated output.
3. Save deterministic physical layouts and frozen numerical identities. A fresh numerical execution gets fresh identities even when the semantic reuse key is equal.
4. Verify exact expected records and bindings before publishing materialization readiness. Partial or incompatible data must not become searchable.
5. Acquire bounded active pins and recheck current health/access at the documented query boundaries. Preparation grants no release authority and does not create a permanent numerical archive.

For R1={A1,B1} and R2={A1,B2}, reuse GA, insert GB2 and keep GB1 while R1 needs it. GA receives no membership write.

Reuse avoids unnecessary numerical work, but checking the complete result still has a cost. Snapshot assembly can read O(documents), and full verification can cost O(chunks). Reuse does not make every build proportional only to changed bytes.

<a id="preserve-numerical-meaning"></a>

## Preserve numerical meaning

Profiles select stable connection IDs and expected vector meaning, not executable historical access settings.

Reject a shared connection update before mutation if prepared or in-progress embedding dependencies would become incompatible or compatibility is unproven. Include hidden/retained dependencies in that check. Aliases, dimensions or a successful probe are insufficient evidence. Never search old vectors with incompatible query embeddings.

Another model remains possible through a distinct appropriate immutable profile/connection and ordinary preparation. Credential-only rotation does not require new vectors by itself. Relevant admitted-access changes stop further dispatch and retain actual access-revision evidence. Provider alias drift cannot always be detected.

<a id="portability-and-evaluation-coordinates"></a>

## Portability and evaluation coordinates

Portable processing profiles use the supported Docling hybrid-chunking option and preserve complete embedding settings. Reject silent truncation. Changed meaning needs a distinct named immutable profile. Export transfers settings rather than vectors or proof that an alias is unchanged.

Exact profile View/Use actions and creator assignments are accepted. No profile Edit or force-deletion workflow follows. Schemas, assets and limits still need qualification.

Indexing supplies source-version/artifact spans and mappings for text actually returned, including truncation. Evaluation owns full-union passage coverage. Changed chunk boundaries can still cover the same passage. Chunk IDs or fuzzy resemblance cannot prove that. Missing mappings are unscorable.

Ragas starter generation reuses processed text without extra generation-time embeddings, reparsing or relationship graphs.

### Apply the accepted coordinate and binding contracts

[PD-INDEXING-01](decision-capability-binding-contracts.md#approved-resolution) selects existing materialization references with complete bounded verified projections and operation-owned pins. [PD-INDEXING-03](decision-source-coordinates.md#approved-resolution) selects canonical conversion identity independent of chunk-only settings and zero-based Unicode code-point half-open ranges. Read those accepted contracts before defining the consuming interfaces. Accepted PD-INDEXING-02/04/05 select current-health observation, physical-erasure policy and parser runtime limits, with qualification still required.

<a id="understand-what-is-shared"></a>

<a id="model"></a>

<a id="1-understand-what-is-shared"></a>

## Understand what is shared

| Component | Responsibility |
| --- | --- |
| **PostgreSQL** | Owns document identities and versions, exact collection revisions, authorization, vector-generation references, materialization readiness, jobs, release pointers, retention, and deletion state. |
| **Chroma** | Stores immutable derived vector records and searches the scope selected by the application. It does not own logical membership or permissions. |
| **SeaweedFS through `ArtifactStore`** | Provides private S3-compatible artifact storage, including referenced manifests and temporary exact retry payloads. PostgreSQL owns their identity and publication. |
| **`ModelGateway`** | Supplies every document and query embedding. Chroma receives explicit embeddings and must not invoke its own provider embedding function. |

In production Docker Compose, Chroma runs as a **private HTTP server**. Clients must not open a shared embedded persistence directory.

Domain code uses `ArtifactStore` and `VectorIndex`, interfaces defined by Inframeld. Storage adapters translate those calls into SeaweedFS or Chroma operations. This keeps vendor-specific details out of the domain.

**Indexing** owns processing results, vectors, shard layouts, and the decision that prepared data is ready. **Pipelines** records which prepared data a pipeline version uses. Application operations coordinate the two. Other modules must ask Indexing about readiness rather than keep their own competing flag.

A status screen can read a summary from PostgreSQL without loading every document. This is the practical purpose of separating queries from commands, also called lightweight CQRS.

<a id="worked-example-one-changed-document-and-two-retained-revisions"></a>

### Worked example: one changed document and two retained revisions

All documents in this example belong to organization O1/project P1. They use processing profile PP1, embedding profile E1, index I, and LAYOUT1. Each document version produces exactly two chunks.

The short labels stand in for real opaque IDs. The illustrated shard assignments are outputs of the recorded placement rule, not a requirement to put one chunk from every document in each shard.

<a id="portable-profiles"></a>

<a id="portable-profile-meaning"></a>

<a id="preserve-processing-and-embedding-settings-during-export"></a>

### Preserve processing and embedding settings during export

If Alice changes chunking, she creates a new named processing profile and explicitly prepares data with it. Processing profiles are immutable. V1 creation of processing/embedding profiles is human-only, using the corresponding Project Create action and separate exact-profile View/Use creator assignments in [the Access contract](../../inframeld-access-models/references/actions-and-initial-grants.md#initial-assignments). Applications can use permitted existing profiles. A changed imported definition requires a human to create a distinct profile. There is no mutable-profile Edit or force-deletion workflow in this decision. Saving a definition neither processes data nor generates vectors. Changing only a prompt or reranker can reuse compatible verified indexes.

The selected processing option is Docling HybridChunker. Its processing and tokenizer assets must have pinned identities and work offline. Keep the supported configuration small and validated, and export the effective settings explicitly. Exact assets, numerical presets and source-coordinate mappings still need qualification.

An embedding profile must describe the complete vector meaning: connection and model, expected dimensions, normalization, distance metric and relevant handling of document and query inputs.

Expected dimensions are an output check, not automatically a request for the provider to resize its vectors. Validate the actual document and query payload sizes. Reject oversized inputs rather than silently truncate them. Successful response validation records evidence without changing the profile. Using a connection's current settings never permits incompatible query vectors to be mixed with prepared data.

The [model-metadata contract](../../inframeld-application-contracts/references/model-validation.md#model-metadata) permits reliable suggestions that users can edit before saving. If a private server provides no usable metadata, ask for the required supported dimensions and input/tokenizer settings. Do not guess that its model matches a public one.

These declarations can complete a configuration, but do not prove that the model works or is compatible with another model. Save the reviewed settings and where they came from. A newer catalogue cannot change an existing profile. Changing the tokenizer, dimensions or any other processing or vector meaning requires a new profile and ordinary preparation.

Do not resize returned vectors or silently choose a generic tokenizer to make them appear compatible. Explain missing required metadata or assets as actionable failures. Synthetic probes remain optional.

[Configuration portability](../../inframeld-application-contracts/references/configuration-export-and-import.md) transfers these definitions, not vectors. Named references resolve to permanent destination IDs. Altered profile meaning needs a distinct name. Settings cannot guarantee future provider-alias stability or identical vectors. The [V1 scope](../../inframeld-architecture/references/v1-scope-and-extension-boundaries.md) explains delivery scope. Exact schema and source-mapping choices stay in their owning pending decisions.

<a id="maintainer-checks"></a>

<a id="7-maintainer-checks"></a>

## Maintainer checks

| Scenario | Expected outcome |
| --- | --- |
| Only the prompt changes | Reuse a compatible ready materialization. |
| B1 becomes B2 | Reuse A/C, create B2's generation, and verify the new revision's complete inventory. |
| One shard times out | Keep the candidate unready. Retry exact saved IDs and bytes within bounds. |
| No generations are permitted | Return the authorized no-evidence result without an unfiltered search. |
| A required shard fails during a query | Fail explicitly. Do not present partial corpus results as complete. |
| A pin times out in SQL while its process still runs | Establish termination or retain protection before cleanup. |
| An old write completes after deletion | The tombstone blocks reuse. Physical cleanup remains pending until proven. |

<a id="pending-decisions-for-dependent-implementation"></a>

## Decision references for dependent implementation

Apply the accepted entries when their scope matches. Evidence and implementation remain separate:

- [PD-INDEXING-03 (accepted): Keep source passage identity stable when chunking changes](decision-source-coordinates.md). Before defining parsed artifact identities, source-span fields, chunk transformation mappings or passage-coverage implementation.
- [PD-INDEXING-05 (accepted): Select and prove a bounded parser runtime](decision-parser-runtime-profile.md). Before fixing parser numerical limits or shipping the assembled parser image/sandbox/host profile.

<a id="status-and-sources"></a>

## Status and sources

Default presets and flexible first-answer timing cannot weaken readiness. Unsupported parser isolation fails without privileged fallback. Chroma never embeds independently. Workload, resource, recall and capacity calculations are qualification plans, not measured guarantees. Do not reopen completed foundations to invent another engine.

- [Indexing model](#model), [readiness](materialization-verification.md#build), [profile portability](#portable-profiles), [embedding compatibility](materialization-verification.md#embedding-compatibility) and [records](records.md#indexing).
- [Ingestion security](../../inframeld-knowledge/references/uploads-and-source-sync.md), [model connections](../../inframeld-application-contracts/references/model-gateway-and-connections.md), [passage identity](../../inframeld-evaluation/references/passage-coverage.md#passages), [Evaluation records](../../inframeld-evaluation/references/records.md#evaluation) and [configuration portability](../../inframeld-application-contracts/references/configuration-export-and-import.md).
- [ADR-0009](../../../../docs/adr/ADR-0009-keep-application-authority-in-postgresql-and-derived-vectors-in-chroma.md), [ADR-0010](../../../../docs/adr/ADR-0010-save-deterministic-layouts-for-vector-shards.md), [ADR-0040](../../../../docs/adr/ADR-0040-bind-pipeline-versions-to-verified-profile-specific-materializations.md), [ADR-0052](../../../../docs/adr/ADR-0052-separate-experimental-execution-from-release-ready-pipeline-builds.md) and [ADR-0054](../../../../docs/adr/ADR-0054-use-shared-current-model-connections.md).
