---
name: inframeld-indexing
description: Explains and reviews Inframeld processing profiles, embeddings, vector reuse, materialization readiness, filtered retrieval and cleanup. Use for index correctness and numerical lifecycle, rather than release authority.
---

# Inframeld Indexing

Explain how admitted source versions become verified, reusable search data. Indexing owns processing/embedding profiles, chunks, numerical generations, saved layouts and materialization readiness. Knowledge owns corpus membership, Access owns current grants and Releases owns publication.

## Working model

Alice replaces B1 with B2 in a corpus containing unchanged A1. Indexing can reuse A1's compatible vectors, create B2's vectors and retain B1's vectors while an older revision needs them. It never edits A1's vectors merely to add new collection membership.

An embedding is a numerical representation used to find similar text. Its profile fixes the meaning of those numbers. A processing profile fixes parsing/chunking settings.

Generations record actual executions. A materialization verifies the exact corpus, profiles and generations a query needs. These are useful distinctions, not a requirement for a class or repository per noun.

PostgreSQL records exact revision membership and authority. Chroma stores immutable derived records in physical collections called shards. A logical Knowledge collection need not match one shard.

## Essential rules

- Search only exact revision membership intersected with current access, using server-generated filters. Empty authorized scope performs no Chroma search. A failed required shard fails visibly.
- Only the singleton worker writer mutates Chroma under its process-lifetime local lock. API handlers do not write vectors.
- Capture exact bounded vector IDs and payload bytes before dispatch. Safe storage retries reuse those bytes and verify actual records. Partial success stays unready.
- A provider timeout before captured embedding bytes does not authorize another paid embedding request. SQL fencing prevents stale publication, not remote execution.
- Reject incompatible or unproven shared embedding changes before mutation. Aliases, dimensions or a probe cannot prove unchanged meaning. Credential-only rotation does not itself require new vectors.
- Pins, retirement and cleanup share the retention gate. Erasure can invalidate old versions. A historical ready label is not current health or final-erasure proof.
- Parsing stays offline in the supported sandbox with pinned assets and validated output. Unsupported isolation has no privileged fallback. Every remote embedding uses ModelGateway.

## Explain or review

1. Show the PostgreSQL, artifact and Chroma state before and after one changed document.
2. Identify what is reused, newly executed, verified, pinned or retired. State the exact identity used for each decision.
3. For retrieval, name membership, current scope, filters, required shards and failure behavior.
4. Distinguish paid-call uncertainty from replaying a frozen storage payload. Explain what a stale attempt can still do remotely.
5. Cite accepted protocols and qualification limits. Inspect implementation before claiming it exists. Loading this skill grants no model-call or mutation authority.

Before domain-specific backend component design, code generation or structural review, read [this module's architecture](references/architecture.md) and the relevant workflow, together with Coding Standards. Its accepted design, inspected implementation and proposals have different status. Resolve a pending architectural choice before suggesting code that depends on it. Behaviour-only questions can go directly to their workflow.

## Read as needed

- For module responsibilities, collaborators, data ownership or component design/review, read [Architecture](references/architecture.md).

- For profiles, source coordinates, compatibility or pre-build preparation, read [Profiles and preparation](references/profiles-and-preparation.md).
- For singleton writes, captured payloads and failure recovery, read [Vector writes and retries](references/vector-writes-and-retries.md).
- For exact filters, fan-out, merging and access changes, read [Retrieval and filtering](references/retrieval-and-filtering.md).
- For pins, tombstones, delayed writes or final cleanup, read [Retirement and erasure](references/retirement-and-erasure.md).

The [Indexing guide](../../../docs/development/indexing.md) owns protocols and qualification calculations. The [Indexing data model](../../../docs/development/data-model.md#indexing) owns records. Do not invent an engine or distributed coordination to preserve a failed backend assumption.
