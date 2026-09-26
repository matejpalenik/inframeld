---
name: inframeld-indexing
description: Explain or review Inframeld processing and embedding profiles, chunks, immutable vector generations, shard layouts, materialization readiness, filtered retrieval and index cleanup. Use for index correctness or reuse; ordinary release decisions belong to Pipelines and Releases.
---

# Inframeld Indexing

Explain how admitted source versions become verified, reusable search data. Indexing owns processing and embedding profiles, generations, layouts, and materialization readiness. Knowledge owns membership; Access owns grants; Releases owns publication.

## Scope and reading route

Default to read-only assistance. Loading this skill grants no edit, model-call, or mutation permission. Start with the relevant protocol, then its record definitions; cite current sources and separate designed guarantees from verified code.

- [Indexing](../../../docs/development/indexing.md) owns writes, filters, verification, reuse, retirement, and qualification calculations. [Indexing records](../../../docs/development/data-model.md#indexing) defines profiles, generations, saved layouts, and materializations.
- Decisions: [PostgreSQL and Chroma](../../../docs/adr/ADR-0009-keep-application-authority-in-postgresql-and-derived-vectors-in-chroma.md), [saved layouts](../../../docs/adr/ADR-0010-save-deterministic-layouts-for-vector-shards.md), [frozen payload retries](../../../docs/adr/ADR-0011-retry-frozen-vector-identities-and-payloads.md), and [verified bindings](../../../docs/adr/ADR-0040-bind-pipeline-versions-to-verified-profile-specific-materializations.md).
- [Ingestion security](../../../docs/development/ingestion-security.md) covers Docling and isolation; [Model connections](../../../docs/development/model-connections.md) covers embedding semantics and egress. Read [Access](../../../docs/development/access-control.md), [Jobs](../../../docs/development/jobs-and-idempotency.md), [Deletion](../../../docs/development/retention-and-deletion.md), or [Onboarding](../../../docs/development/onboarding.md) when crossing those boundaries.
- [Maintainer checks](../../../docs/development/indexing.md#maintainer-checks) summarize reuse, failure, and cleanup scenarios.

- For reuse, start with [shared generations](../../../docs/development/indexing.md#model), then [readiness](../../../docs/development/indexing.md#build). For uncertainty, distinguish [saved-payload retries](../../../docs/development/indexing.md#retries) from [final cleanup](../../../docs/development/indexing.md#retirement).

## Essential boundaries

A ProcessingProfile fixes parser/chunker inputs; a ProcessingGeneration records actual output for one DocumentVersion. Chunks carry source spans. An EmbeddingProfile fixes numerical meaning. A semantic Vectorization is a reuse key; a physical VectorGeneration identifies one actual numerical execution. A VectorIndex has a saved layout of physical Chroma collections, or shards. An IndexMaterialization verifies exact revision/profile/generation bindings. These concepts do not require an aggregate or repository each.

PostgreSQL owns exact revision membership and current policy. Chroma holds immutable derived records, never mutable membership arrays, group lists, or serving flags. Logical collections and physical shards are not one-to-one.

For R1={A1,B1} and R2={A1,B2}, reuse GA, insert GB2, and retain GB1 while R1 needs it. GA receives no membership write. Snapshot assembly may still read O(documents), and verification O(chunks); numerical reuse does not make every build proportional only to changes. A fresh numerical execution gets fresh identities. Changing embedding meaning creates a profile; credential-only rotation does not. Prompt-only changes can reuse a ready materialization.

The singleton vector writer stays in the existing worker with its process-lifetime local lock. API handlers do not mutate Chroma. Freeze exact bounded IDs and payload bytes before dispatch; retries use those same bytes, verify actual records, then conditionally publish readiness. Partial success remains unready. A provider timeout before captured bytes does not authorize another paid embedding request. SQL fencing protects publication, not cancellation of external work.

Queries intersect exact revision membership with current access and use server-generated filters. Empty scope makes no Chroma search. Failed required shards fail visibly. Merge comparable results with bounded fan-out and stable ties; global top-k followed only by permission checks is insufficient. Pins and ordinary retirement share the SQL retention gate; current health and access are rechecked at the documented boundaries.

Retired physical identities are permanently tombstoned before cleanup. Delayed writes can recreate unreachable bytes, so observing absence once is not proof of final erasure. Ordinary frozen retries do not require routine Chroma restart; corruption and unresolved cleanup can require intervention. A ready label is not proof of current health. Erasure can invalidate old releases, while ordinary expiry respects references.

Parsing remains offline inside the per-attempt sandbox with pinned assets and validated output. Unsupported isolation fails without privileged fallback. Chroma never embeds independently; embeddings use ModelGateway. Default presets and the flexible first-answer timing goal never weaken readiness.

## Explain and review

Show PostgreSQL, Chroma, and artifact state before and after one changed document. For a query, identify membership, current scope, filter, required shards, and failure. Use the guide’s failure, recall, and resource qualification plans without claiming they have run. Reconsider a failed backend assumption instead of adding unbounded filter splitting, distributed coordination, or another search engine.
