---
name: inframeld-indexing
description: Explain or review Inframeld processing and embedding profiles, chunks, immutable vector generations, shard layouts, materialization readiness, filtered retrieval and index cleanup. Use for index correctness or reuse; ordinary release decisions belong to Pipelines and Releases.
---

# Inframeld Indexing

Help the developer explain how admitted source versions become verified, reusable search data. Indexing owns profiles, processing results, vector generations, layouts and materialization readiness. It does not own document membership, permission grants, model credentials or release authority.

## Scope and sources

Default to read-only assistance; this skill grants no file-edit or mutation permission. Resolve paths from the repository root. Read the guide's vector, build and serving sections and the relevant protocol before assessing a detail.

- `docs/ARCHITECTURE.md` is the human explanation.
- `docs/adr/ADR-0004-postgresql-source-of-truth-and-shared-chroma.md` owns physical identity, writer/retry/filter/retirement rules and qualification.
- `docs/adr/ADR-0015-profile-specific-index-materializations-and-pipeline-bindings.md` owns profiles, materializations and binding readiness; ADR-0003 owns lineage.
- `docs/adr/ADR-0010-secure-document-ingestion-boundary.md` and `docs/adr/ADR-0016-docling-processing-and-cross-encoder-reranking.md` own processor isolation and built-in adapter behavior.
- Read ADR-0005/0006 for access/gateway, ADR-0007 for job attempts, and ADR-0014 for deletion when the task crosses those boundaries. ADR-0019 owns the default default automatic path and reversible publication modes; neither weakens readiness.

## Language and consistency boundaries

A ProcessingProfile fixes parser/chunker inputs; a ProcessingGeneration records their output for a DocumentVersion. Chunks carry source spans. An EmbeddingProfile fixes numerical meaning, including dimensions and model/connection revision. A semantic Vectorization is a reuse key. A physical VectorGeneration identifies one actual immutable numerical execution. A VectorIndex records the scoped namespace; its saved layout names physical Chroma collections acting as shards. An IndexMaterialization verifies exact revision/profile/generation bindings.

Profiles, generation state, index/layout and materialization publication are conceptual consistency boundaries. Shards, chunk rows and manifest entries are not automatically separate aggregates. Do not invent a class hierarchy or load the corpus through a root object; use bounded application/repository operations.

## Invariants to apply

1. PostgreSQL owns exact revision membership and current policy. Chroma stores immutable derived records, never mutable `collection_revision_ids`, group lists or a serving flag. Logical and physical collections are not one-to-one.
2. With R1={A1,B1} and R2={A1,B2}, reuse GA and insert GB2; keep GB1 while R1 needs it. No GA membership write occurs. Snapshot assembly can still read O(documents), and verification can read O(chunks). Do not claim total build work depends only on changed documents.
3. A fresh numerical execution receives new generation/record identities. Reusing semantic inputs does not authorize overwriting retained vectors. Changing embedding semantics creates a profile; rotating only a credential does not. Prompt-only changes can reuse a whole ready materialization.
4. The singleton vector writer lives in the existing worker and holds the documented process-lifetime local lock. API handlers do not mutate Chroma. PostgreSQL fences guard SQL publication, not external request execution.
5. Freeze exact bounded payloads before Chroma dispatch. Retry identical IDs and bytes, verify actual records, then conditionally publish readiness. Partial success remains unready. A provider timeout before bytes are captured is not permission to call the embedding model again automatically.
6. Query-time scope is exact revision membership intersected with current access. The server builds generation filters. Empty scope makes no Chroma search; failed required shards fail visibly. Merge comparable results with bounded fan-out and stable ties. Never replace filtering with global top-k followed only by permission checks.
7. Query pins and ordinary retirement share a SQL retention gate. Health and access are rechecked at documented dispatch/disclosure boundaries. Erasure can invalidate retained releases; routine expiry must respect live references.
8. Tombstone a retired physical identity permanently before cleanup. A delayed insert can recreate unreachable bytes after deletion; absence once observed does not prove final cleanup. Ordinary immutable retries need no routine Chroma restart, but corrupt/missing payloads and unresolved final erasure can require intervention. Do not overstate automatic recovery.
9. Parsing stays in the offline per-attempt sandbox. Pin required assets; reject untrusted output and unsupported hosts without privileged fallback. Chroma never embeds independently; every embedding uses ModelGateway.

## Lifecycle and task method

Distinguish requested/indexing/ready/failed, later stale/unavailable dependencies, and retirement from physical cleanup. A previously ready label is not current health. The planned initial path may choose a preset and no reranker, but cannot skip materialization verification. The first-answer scenario is an accepted, flexible usability goal: two minutes is aspirational, around ten minutes is acceptable, and neither is measured. It is separate from the larger capacity envelope; no hard 120-second gate or readiness shortcut follows from it.

For a reuse/recovery question, draw the small PostgreSQL/Chroma/artifact state before and after one changed document. For a query question, state membership, current actor scope, generated filter, required shards and failure outcome. Use ADR-0004's existing failure/recall/resource tests; do not invent measured capacity. Reconsider a failed backend assumption rather than rescue it with unbounded filter splitting, a distributed coordinator or a new search engine.
