# Indexing architecture: prepare exact data and prove it is usable

Alice replaces B1 with B2. The old revision still needs B1's vectors, while the new revision can reuse unchanged A1's vectors. Indexing must prepare only the required new data and prove each selected revision has its complete search bindings.

## What Indexing owns

Indexing owns processing/embedding profiles, processed chunks, numerical generations, physical vector layouts, materialization readiness, permission-filtered retrieval and numerical cleanup. Knowledge supplies admitted source versions and exact membership. Access supplies current permissions. Pipelines requests preparation or retrieval. Releases owns traffic.

A profile fixes settings. A generation identifies actual processing or numerical execution. A materialization is the verified collection of exact source, profile and generation bindings needed to search. These concepts do not each require an aggregate, repository or runtime process.

## Main parts and boundaries

**Accepted responsibility view.** The boxes describe logical capabilities, not implemented types.

```mermaid
---
title: "Indexing responsibilities - accepted design"
---
flowchart TB
    Corpus["Knowledge<br/>Exact admitted source versions"] -->|"Captured corpus and selected profiles"| Prepare["Preparation coordination"]
    Prepare -->|"Bounded untrusted input"| Parser["Restricted parser<br/>Offline conversion and chunking"]
    Prepare -->|"Missing embeddings"| Gateway["ModelGateway"]
    Parser -->|"Validated chunks and source coordinates"| Generations["Processing and vector generations"]
    Gateway -->|"Captured numerical output"| Generations
    Generations -->|"Frozen IDs and payload bytes"| Writer["Singleton worker vector writer"]
    Writer -->|"Insert and read back exact records"| Chroma["Private Chroma shards"]
    Chroma -->|"Verified expected records"| Materialization["Materialization readiness"]
    Materialization -->|"Exact usable bindings"| Retrieval["Filtered retrieval under current access"]
    Retirement["Pins, tombstones and cleanup"] -->|"Control retained numerical lifetime"| Generations
```

Arrows describe data and lifecycle responsibilities. PostgreSQL owns membership, current authority and recorded readiness. Private SeaweedFS artifacts hold processed outputs and exact retry bytes through `ArtifactStore`. Chroma stores derived immutable vectors. A logical Collection is not a physical Chroma shard. API code may read through the retrieval path, while only the supported singleton worker writer mutates Chroma under its process-lifetime lock.

## Follow changed content and an uncertain write

**Accepted target workflow.** GA is A1's retained compatible generation. The new revision selects GA and a new GB2. GB1 remains while R1 needs it.

```mermaid
---
title: "Captured vector writes - accepted recovery protocol"
---
sequenceDiagram
    participant P as Captured Pipeline request
    participant I as Indexing preparation
    participant G as ModelGateway
    participant DB as PostgreSQL identities and publication
    participant Store as Private SeaweedFS through ArtifactStore
    participant W as Singleton vector writer
    participant C as Chroma shards
    P->>I: Prepare R2 with exact profiles
    I->>DB: Resolve compatible GA and missing B2 work
    I->>G: Request authorised missing embeddings
    alt Provider outcome uncertain before bytes captured
        G-->>I: Timeout or missing response
        Note over I,DB: Record uncertainty, no automatic paid redispatch
    else Output captured
        G-->>I: Numerical output
        I->>Store: Save bounded exact IDs and payload bytes with checksums
        I->>DB: Durably record batch references before dispatch
        I->>W: Dispatch saved vector batch
        W->>C: Insert frozen records
        alt Storage result uncertain
            Note over W,C: Retry only saved IDs and bytes, then inspect actual records
        end
        W->>C: Read back and verify exact expected records
        W-->>I: Verification outcome
        I->>DB: Conditionally publish readiness after complete verification
    end
```

A storage retry reuses known bytes. A provider timeout before those bytes exist cannot do so. Idempotency recognises original work, and attempt/revision checks stop an obsolete result publishing. They cannot cancel an already sent request. Partial storage success remains unready.

A prompt-only change may reuse a compatible ready materialization. Changing embedding meaning needs a distinct appropriate profile/connection and ordinary preparation. Reject incompatible or unproven shared embedding changes before activation. An alias, matching dimensions or a successful probe cannot prove unchanged numerical meaning.

## Data and execution

Parsing is offline with pinned assets, bounded input/output and worker validation. Unsupported isolation fails without privileged fallback. Every remote embedding uses ModelGateway. Store source/artifact coordinates for text actually returned so Evaluation can measure passage coverage.

A query intersects exact revision membership with current access using server-generated filters. Empty authorised scope performs no Chroma search. A failed required shard fails visibly. Never replace either case with an unfiltered search.

Pins record that work still needs retained data. Tombstones retire identities before resumable deletion, including protection from late writes. Authorised erasure can invalidate historical versions. A historical ready label is not current dependency health or proof of complete erasure.

## What exists today

This is accepted Indexing design. It does not claim an implemented parser coordinator, vector writer or retrieval service. Existing worker/backend assumptions still need the source-specific backend, security, failure and resource qualification in the guide. Reuse does not make full verification free or establish measured capacity.

Read [profiles and preparation](profiles-and-preparation.md), [frozen vector retries](vector-writes-and-retries.md), [retrieval](retrieval-and-filtering.md) and [retirement](retirement-and-erasure.md) for their precise rules.

## Decisions still needed and sources

[ADR-0076](../../../../docs/adr/ADR-0076-separate-index-preparation-retrieval-and-retirement.md) accepts focused preparation/readiness, retrieval and numerical retirement capabilities. The [owning guide](../../../../docs/development/indexing.md#indexing-capability-boundaries) retains exact trusted-input/binding contracts, current-health obligations, unavailable outcomes and cleanup coordination still to specify. The selected engine, frozen-byte retries and qualification limits remain in force.

[The Indexing guide](../../../../docs/development/indexing.md), [Indexing records](../../../../docs/development/data-model.md#indexing), [model connections](../../../../docs/development/model-connections.md) and [ingestion security](../../../../docs/development/ingestion-security.md) own the accepted protocols and qualification limits.
