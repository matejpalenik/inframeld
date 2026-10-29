# Knowledge architecture: preserve which source version was accepted

<a id="knowledge-architecture-preserve-which-source-version-was-accepted"></a>

Alice replaces Support handbook B1 with B2 while a question still uses R1={A1,B1}. Knowledge must preserve the earlier selection and make a new version available for later work. It also has to control who may upload, replace, share or erase the content.

<a id="what-knowledge-owns"></a>

## What Knowledge owns

Knowledge owns source identity, Documents, immutable DocumentVersions, Collections, exact CollectionRevisions, admission and bounded source synchronisation. A Document is the logical source. A DocumentVersion identifies fixed bytes. A CollectionRevision freezes exact versions for an operation.

Access owns current permission. Indexing owns processing and verified search data. Pipelines captures execution inputs and builds ready versions. Releases selects traffic. Admitting B2 alone changes none of those other owners' decisions.

<a id="main-parts-and-boundaries"></a>

## Main parts and boundaries

**Accepted responsibility view.** These are capabilities to implement, not inspected classes or an aggregate per box.

```mermaid
---
title: "Knowledge responsibilities - accepted design"
---
flowchart TB
    Entry["Upload or explicit source sync"] -->|"Bounded complete source input"| Admission["Knowledge admission<br/>Validate source identity and durable bytes"]
    Admission -->|"Require current mutation permission"| Access["Access"]
    Admission -->|"Store immutable content through artifact capability"| Artifacts["Private staging and artifact storage"]
    Admission -->|"Record source and version identities"| Documents["Document and version lifecycle"]
    Documents -->|"Freeze exact selected versions"| Collections["Collection revision lifecycle"]
    Collections -->|"Supply exact corpus"| Prepare["Indexing preparation"]
    Documents -->|"Change availability and coordinate erasure"| Deletion["Knowledge deletion and retention"]
```

Arrows describe responsibility hand-offs. They do not prescribe a public API or import graph. An artifact is stored content. Storing an object is not admission until the owning workflow has verified complete durable content and saved its authorised meaning.

<a id="follow-a-replacement"></a>

## Follow a replacement

**Accepted target workflow.** A document audience is its saved nonempty list of permitted access groups. Alice needs Update documents on every saved group to replace it. Existing read work has captured R1. In this example Alice also selects B2 for a new revision through an authorised selection or complete-batch workflow.

```mermaid
---
title: "Document replacement and selection - accepted behaviour"
---
sequenceDiagram
    actor Alice
    participant K as Knowledge workflow
    participant A as Access
    participant Store as Artifact capability
    participant DB as Authoritative records
    participant I as Indexing
    Alice->>K: Replace B with complete supported bytes
    K->>A: Require replacement authority for current audience
    K->>Store: Stage and verify complete durable bytes
    alt Incomplete or invalid input
        Note over K,DB: Reject admission, create no usable version
    else Valid input
        Note over K,DB: Short coordinated write and current authority recheck
        K->>DB: Reuse equal authoritative content or record B2
        Note over DB: Persist admission with its required metadata and audit
        opt Explicitly authorised corpus selection or complete-batch workflow
            K->>DB: Conditionally commit R2, complete marker and durable handoff
            opt Explicit preparation or authorised automatic workflow
                K->>I: Recover ordinary admission from durable handoff
            end
        end
        Note over K,I: External waits are outside SQL, publication stays separate
    end
```

The new selection is explicit or comes from the accepted complete-batch workflow. Replacing content does not silently retarget every collection or admitted execution. For changed content, R2={A1,B2} leaves R1 fixed. Equal authoritative content may reuse a version, subject to the same authorization and non-disclosure rules.

An admitted operation is work the server has durably accepted. A lost response uses that original operation and saved artifacts. It does not permit a second source or an uncertain paid retry. Source sync preserves source identity and checkpoints. An incomplete inventory cannot prove that an unseen object disappeared.

<a id="data-and-execution"></a>

## Data and execution

PostgreSQL owns identities, exact membership and authority. SeaweedFS holds immutable source and derived artifacts through application-owned capabilities. Filenames are display labels, not storage paths or authority. Parsing runs later in the restricted processing boundary under Indexing's profiles.

Document audiences are nonempty and project-local. Reading requires ordinary membership in at least one allowed group. Replacement requires Update documents on every saved audience group and preserves that audience. Sharing is separately authorised human work requiring management of every old and new group. Add, read, replace and erase remain different permissions. Changed audience or authority is rechecked before the applicable change commits. A source credential does not import upstream access lists into Inframeld. Configuration import does not contact the source automatically.

Removing B from a future selection differs from erasing B. Erasure first blocks prohibited access and then coordinates resumable physical cleanup with Indexing and artifact retention. Old queries, citations and evaluation evidence remain subject to current access and erasure. Immutable identity promises a fixed reference, not permanent availability.

<a id="what-exists-today"></a>

## What exists today

This is accepted design, not a delivered Knowledge module. The inspected backend source has Access, shared and bootstrap foundations. Source admission, synchronisation, durable artifacts and deletion still need their domain-specific implementation and qualification. Existing generic infrastructure does not qualify those complete workflows.

Read [documents and collections](documents-and-collections.md), [uploads and source sync](uploads-and-source-sync.md) and [deletion and retention](deletion-and-retention.md) for applicable rules. Do not infer a service, repository or table for each named concept.

<a id="decisions-still-needed-and-sources"></a>

## Decisions still needed and sources

[ADR-0075](../../../../docs/adr/ADR-0075-separate-document-lifecycle-from-collection-selection.md) accepts focused document/version and collection-selection operations coordinated by an application workflow for complete batches. The [owning guide](#knowledge-operation-boundaries) links the accepted [PD-KNOWLEDGE-01](decision-complete-batch-handoff.md#approved-resolution) transaction, completeness and durable-handoff contract, with implementation and qualification unfinished. This accepted split adds no schema or API and does not make replacement select a new corpus implicitly.

[Knowledge lifecycle](documents-and-collections.md), [ingestion security](uploads-and-source-sync.md), [Knowledge records](records.md#knowledge) and [retention](deletion-and-retention.md) remain authoritative. The proposed component split must preserve their accepted behaviour.

<a id="proposed-internal-architecture---awaiting-decisions"></a>

<a id="internal-architecture-decisions"></a>

## Internal architecture decisions

The component boundaries below are accepted. They explain how to divide responsibilities inside the existing backend. Accepted detailed contracts are linked below. Separately pending decisions retain their own triggers. Accepted behavior elsewhere in this guide continues to own permissions, lifecycle and failure rules.

<a id="knowledge-operation-boundaries"></a> <a id="proposal-knowledge-boundaries"></a>

<a id="separate-document-lifecycle-from-collection-selection"></a>

### Separate document lifecycle from collection selection

**Status:** Accepted in [ADR-0075](../../../../docs/adr/ADR-0075-separate-document-lifecycle-from-collection-selection.md), with implementation and qualification unfinished.

Document/version lifecycle and exact collection selection have separate application operations. When Alice replaces B1 with B2, the document operation admits the new immutable version. An authorized selection or complete-batch workflow freezes a new collection revision, while earlier R1 membership stays fixed.

A coordinating application workflow handles complete batches spanning both responsibilities. The accepted [PD-KNOWLEDGE-01](decision-complete-batch-handoff.md#approved-resolution) supplies its consistency/handoff contract and preserves the existing atomic admission, audience, durable-content and retry requirements. A manifest remains an inventory, not a mandatory aggregate. Separate operations do not require separate transactions.

**Accepted contract, implementation and qualification pending.** Preserve original child admissions. Conditionally finalize the complete fixed membership and durable continuation under the expected selection revision. Recover the same committed result, or report a concurrent-selection conflict without retargeting. Separate operations do not imply separate commits or permission to expose a partial batch as complete. Indexing preparation and Releases publication keep their own authority and lifetimes.

<a id="pending-decisions-for-dependent-implementation"></a>

## Decision references for dependent implementation

Apply accepted entries when their scope matches. Discuss only choices still explicitly pending:

- [PD-KNOWLEDGE-01 (accepted): Finalize a complete collection selection without losing admitted input](decision-complete-batch-handoff.md). Before implementing batch completion, collection selection, parent/child recovery or the ingestion-to-automatic-update handoff.
- [PD-KNOWLEDGE-02: Choose bounded retention without weakening explicit erasure](decision-retention-erasure-policy.md). Before implementing retention configuration, bounded history storage, expiry or cross-domain source-erasure cleanup.
