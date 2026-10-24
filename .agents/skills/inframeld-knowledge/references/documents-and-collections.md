# Documents, collections and frozen inputs

Alice replaces the Support handbook while a query is already running. The running query must keep the evidence it captured. New work may use the replacement after ordinary preparation. Knowledge provides the identities that make this distinction possible.

## Source identity and version identity

A Document identifies a logical source. A DocumentVersion identifies immutable bytes. A Collection selects a corpus, and a CollectionRevision fixes exact versions. For R1={A1,B1}, replacing B gives B2 and R2={A1,B2}. R1 remains unchanged. Retained Pipeline inputs follow exact versions rather than a mutable latest pointer.

Re-observing authoritative equal content reuses the version. Changed bytes create another. Names and filenames are not stable identity, and arbitrary S3 ETags are not content checksums. Preserve original source identity and current groups during replacement. Do not rewrite earlier versions.

## Capture inputs before preparation

1. Select exact authorized collection/source revisions for the operation.
2. Capture them before direct-query or evaluation preparation. The operation need not create a release-ready PipelineVersion.
3. Ask Indexing to prepare or reuse compatible data under the selected profiles. The same admitted bytes may support another profile without another upload.
4. Preserve that captured corpus throughout an admitted query or evaluation. Concurrent working-configuration edits and source replacements cannot silently retarget it.

Development-only uploads use ordinary collections outside live-watched inputs. Do not silently clone collections or suppress their normal automatic updates. Document-triggered live work retains the Deployment's selected configuration, not an unrelated working edit.

## Portable configuration and generated cases

Configuration export transfers definitions, not document bytes or vector backups. Imported collections are empty, and reusing a collection does not alter its contents. Collection view/edit/delete and Source configuration/sync/credential/deletion actions remain separate. Retiring a Source or Collection does not erase admitted Documents.

A manifest inventories identities and fingerprints. It neither grants access nor proves numerical materialization readiness. Avoid loading a whole large collection into memory or creating an aggregate/repository for every noun.

Evaluation owns generated questions, reference answers and case review. Generation samples permitted frozen versions across documents and sections, not only successful retrieval hits. Those derived excerpts retain source access and erasure obligations. Replacing B1 with B2 must not retarget an existing expected passage. Erasure can instead make it unavailable. Evaluation dataset transfer is separate from corpus admission.

## Failures, status and sources

An unavailable or erased dependency may invalidate historical query inputs or releases. Frozen identity does not authorize reconstruction from newer sources. Upload completion cannot declare an index ready. These are accepted lifecycle rules, not evidence that all routes, storage schemas or first-use behavior are implemented.

- [Knowledge lifecycle](../../../../docs/development/knowledge-lifecycle.md), [frozen corpus](../../../../docs/development/knowledge-lifecycle.md#corpus), [portable Knowledge resources](../../../../docs/development/knowledge-lifecycle.md#portable-knowledge) and [Knowledge records](../../../../docs/development/data-model.md#knowledge).
- [Configuration portability](../../../../docs/development/configuration-portability.md), [Access capability catalogue](../../../../docs/development/access-contracts.md#capability-catalogue) and [CLI delivery](../../../../docs/development/cli-delivery-plan.md).
- [Evaluation generation](../../../../docs/development/evaluation.md#generation), [protected history](../../../../docs/development/evaluation.md#history), [ADR-0008](../../../../docs/adr/ADR-0008-preserve-immutable-versions-and-their-provenance.md) and [ADR-0052](../../../../docs/adr/ADR-0052-separate-experimental-execution-from-release-ready-pipeline-builds.md).
