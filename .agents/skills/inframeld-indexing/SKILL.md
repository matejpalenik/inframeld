---
name: inframeld-indexing
description: Explains and reviews Inframeld processing profiles, embeddings, vector reuse, materialization readiness, filtered retrieval and cleanup. Use for index correctness and numerical lifecycle, rather than release authority.
---

# Inframeld Indexing

Explain how admitted source versions become verified, reusable search data. Indexing owns processing/embedding profiles, chunks, numerical generations, saved layouts and materialization readiness. Knowledge owns corpus membership, Access owns current grants and Releases owns publication.

## Working model

Alice admits B2 and an authorized collection selection replaces B1 with it, keeping unchanged A1. Indexing can reuse A1's compatible vectors, create B2's vectors and retain B1's vectors while an older revision needs them. It never edits A1's vectors merely to add new collection membership.

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

For backend component design, code generation or structural review, read [module architecture](references/architecture.md), the affected workflow and Coding Standards. Behavior-only questions go directly to their workflow. Pending proposals do not authorize dependent code.

## Pending decisions for affected work

Load only matching triggers. Discuss and obtain approval before code depends on an unresolved choice, following [decision finalization](../../../docs/development/guides/architecture-decisions.md). Unrelated decisions do not block work. Qualification gaps gate claims, not evidence-gathering tests.

- [PD-INDEXING-01](references/decision-capability-binding-contracts.md): Before defining preparation, retrieval or retirement application ports and their complete input/result records.
- [PD-INDEXING-02](references/decision-health-observation.md): Before implementing reconciliation, ongoing serving-health checks or claims about how quickly storage loss is detected.
- [PD-INDEXING-03](references/decision-source-coordinates.md): Before defining parsed artifact identities, source-span fields, chunk transformation mappings or passage-coverage implementation.
- [PD-INDEXING-04](references/decision-storage-retries-and-erasure.md): When implementing frozen-write retry/retirement adapters, selecting artifact completion mechanics or qualifying final-erasure claims.
- [PD-INDEXING-05](references/decision-parser-runtime-profile.md): Before fixing parser numerical limits or shipping the assembled parser image/sandbox/host profile.

## Read as needed

Choose the row matching the task. Workflow, contract and architecture views are separate reading units. Do not load this whole table.

| Task | Direct reference |
| --- | --- |
| Module/component design or structural review | [Indexing architecture: prepare exact data and prove it is usable](references/architecture.md) |
| Materialization verification | [Verify the exact prepared search data](references/materialization-verification.md) |
| Parser isolation and validation | [Process untrusted documents in a restricted runtime](references/parser-isolation-and-validation.md) |
| Profiles and preparation | [Profiles, generations and verified preparation](references/profiles-and-preparation.md) |
| Logical records and representation ownership | [Index profiles, generations and bindings](references/records.md) |
| Retirement and erasure | [Retire numerical data without restoring access](references/retirement-and-erasure.md) |
| Retrieval and filtering | [Search only the permitted corpus](references/retrieval-and-filtering.md) |
| Vector writes and retries | [Vector writes and frozen-payload retries](references/vector-writes-and-retries.md) |

## Source ownership

Focused references own accepted behavior and logical design. Code, generated OpenAPI and migrations own implemented representations. Read exact definitions when fields matter, ADRs for rationale or conflicts, and matching pending decisions before dependent design. Human guides own development procedures.
