# Profiles, generations and verified preparation

Alice changes chunking while keeping the same handbook bytes. She needs another preparation result, not another upload. A prompt-only change may instead reuse an existing ready materialization. Indexing distinguishes source identity, requested meaning and actual numerical execution.

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

## Prepare exact inputs

1. Capture the complete authorized corpus and profiles. A direct query or evaluation can prepare a working-configuration snapshot without creating a PipelineVersion. It must not mutate live vector generations.
2. Reuse exact compatible generations or perform ordinary new processing and gateway-controlled embeddings. Parsing remains offline in the per-attempt sandbox with pinned assets and validated output.
3. Save deterministic physical layouts and frozen numerical identities. A fresh numerical execution gets fresh identities even when the semantic reuse key is equal.
4. Verify exact expected records and bindings before publishing materialization readiness. Partial or incompatible data must not become searchable.
5. Acquire bounded active pins and recheck current health/access at the documented query boundaries. Preparation grants no release authority and does not create a permanent numerical archive.

For R1={A1,B1} and R2={A1,B2}, reuse GA, insert GB2 and keep GB1 while R1 needs it. GA receives no membership write.

Reuse avoids unnecessary numerical work, but checking the complete result still has a cost. Snapshot assembly can read O(documents), and full verification can cost O(chunks). Reuse does not make every build proportional only to changed bytes.

## Preserve numerical meaning

Profiles select stable connection IDs and expected vector meaning, not executable historical access settings.

Reject a shared connection update before mutation if prepared or in-progress embedding dependencies would become incompatible or compatibility is unproven. Include hidden/retained dependencies in that check. Aliases, dimensions or a successful probe are insufficient evidence. Never search old vectors with incompatible query embeddings.

Another model remains possible through a distinct appropriate immutable profile/connection and ordinary preparation. Credential-only rotation does not require new vectors by itself. Relevant admitted-access changes stop further dispatch and retain actual access-revision evidence. Provider alias drift cannot always be detected.

## Portability and evaluation coordinates

Portable processing profiles use the supported Docling hybrid-chunking option and preserve complete embedding settings. Reject silent truncation. Changed meaning needs a distinct named immutable profile. Export transfers settings rather than vectors or proof that an alias is unchanged.

Exact profile View/Use actions and creator assignments are accepted. No profile Edit or force-deletion workflow follows. Schemas, assets and limits still need qualification.

Indexing supplies source-version/artifact spans and mappings for text actually returned, including truncation. Evaluation owns full-union passage coverage. Changed chunk boundaries can still cover the same passage. Chunk IDs or fuzzy resemblance cannot prove that. Missing mappings are unscorable.

Ragas starter generation reuses processed text without extra generation-time embeddings, reparsing or relationship graphs.

## Status and sources

Default presets and flexible first-answer timing cannot weaken readiness. Unsupported parser isolation fails without privileged fallback. Chroma never embeds independently. Workload, resource, recall and capacity calculations are qualification plans, not measured guarantees. Do not reopen completed foundations to invent another engine.

- [Indexing model](../../../../docs/development/indexing.md#model), [readiness](../../../../docs/development/indexing.md#build), [profile portability](../../../../docs/development/indexing.md#portable-profiles), [embedding compatibility](../../../../docs/development/indexing.md#embedding-compatibility) and [records](../../../../docs/development/data-model.md#indexing).
- [Ingestion security](../../../../docs/development/ingestion-security.md), [model connections](../../../../docs/development/model-connections.md), [passage identity](../../../../docs/development/evaluation.md#passages), [Evaluation records](../../../../docs/development/data-model.md#evaluation) and [configuration portability](../../../../docs/development/configuration-portability.md).
- [ADR-0009](../../../../docs/adr/ADR-0009-keep-application-authority-in-postgresql-and-derived-vectors-in-chroma.md), [ADR-0010](../../../../docs/adr/ADR-0010-save-deterministic-layouts-for-vector-shards.md), [ADR-0040](../../../../docs/adr/ADR-0040-bind-pipeline-versions-to-verified-profile-specific-materializations.md), [ADR-0052](../../../../docs/adr/ADR-0052-separate-experimental-execution-from-release-ready-pipeline-builds.md) and [ADR-0054](../../../../docs/adr/ADR-0054-use-shared-current-model-connections.md).
