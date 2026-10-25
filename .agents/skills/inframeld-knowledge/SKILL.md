---
name: inframeld-knowledge
description: Explains and reviews Inframeld documents, immutable versions, collections, uploads, source sync and deletion. Use for knowledge lifecycle and upload onboarding, rather than numerical index protocols.
---

# Inframeld Knowledge

Explain how source information becomes admitted product knowledge. Knowledge owns source identity, Documents, immutable DocumentVersions, Collections, exact CollectionRevisions, upload admission and source synchronization. Indexing owns verified search readiness. Releases owns publication.

## Working model

Alice uploads two Support documents, A1 and B1. A Document is the stable identity of a logical source. A DocumentVersion identifies the immutable bytes observed for it.

A Collection groups documents. A CollectionRevision freezes exact versions, forming a corpus, the source material selected for an operation.

If Alice replaces B1 with B2, the new revision is R2={A1,B2}. The earlier R1={A1,B1} does not change. That lets a retained query explain which source version it used. Replacing a source, removing it from a new corpus and erasing its history are different operations.

Uploaded, admitted, parsed and searchable are different milestones. Admission means the application has accepted complete validated source input. Parsing and embeddings belong to later preparation. Indexing can prepare another profile without another upload.

## Essential rules

- Admit only complete bounded supported input through private staging and durable artifact verification. Filenames are display text, not storage keys or identity.
- Re-observing authoritative equal content reuses its version. Changed bytes create another version. Arbitrary S3 ETags are not content checksums.
- Document audiences are explicit, same-project and nonempty. Upload, replacement, sharing and deletion require their own current permissions.
- Historical versions, downloads and citations remain subject to current access and erasure. Immutable identity does not promise permanent availability.
- Source sync uses approved saved scope and current mutation authority. It does not import upstream ACLs or infer complete absence from an incomplete inventory.
- Complete authorized batches can feed normal automatic-update workflows. Partial uploads, upload-only rights and unrelated working edits cannot acquire release authority.
- A manifest records identities and fingerprints. It is not a permission authority or numerical vector backup. A concept does not require its own aggregate or repository.

## Explain or review

1. Start with two documents and one replacement, a duplicate retry, or a deletion during preparation.
2. Name the source, version, collection revision and owner at each step. Explain which identities remain fixed.
3. Check current permissions at the documented admission/commit boundaries. Explain the effect on existing queries and retained versions.
4. Separate knowledge admission from index preparation, evaluation-case generation and release selection.
5. Cite the current rule and distinguish accepted design from inspected code. Loading this skill authorizes no edits, source contact or external mutations. Report contradictions instead of resolving policy by invention.

Before domain-specific backend component design, code generation or structural review, read [this module's architecture](references/architecture.md) and the relevant workflow, together with Coding Standards. Its accepted design, inspected implementation and proposals have different status. Resolve a pending architectural choice before suggesting code that depends on it. Behaviour-only questions can go directly to their workflow.

## Pending decisions for affected work

Read only entries whose triggers match the proposed design, code suggestion or implementation. Explain the unresolved choice and discuss it with the developer before code depends on it. Qualification gaps gate the stated claims, not tests needed to gather evidence. Follow [the approval and consistency workflow](../../../docs/development/documentation-maintenance.md#just-in-time-architecture-decisions). Unrelated entries do not block work.

- [PD-KNOWLEDGE-01](references/decision-complete-batch-handoff.md): Before implementing batch completion, collection selection, parent/child recovery or the ingestion-to-automatic-update handoff.
- [PD-KNOWLEDGE-02](references/decision-retention-erasure-policy.md): Before implementing retention configuration, bounded history storage, expiry or cross-domain source-erasure cleanup.

## Read as needed

- For module responsibilities, collaborators, data ownership or component design/review, read [Architecture](references/architecture.md).

- For versions, frozen corpora, manifests or portable configuration, read [Documents and collections](references/documents-and-collections.md).
- For staged uploads, replacement, private setup or bounded sync, read [Uploads and source sync](references/uploads-and-source-sync.md).
- For sharing, erasure, late jobs or retained evidence, read [Deletion and retention](references/deletion-and-retention.md).

The [Knowledge guide](../../../docs/development/knowledge-lifecycle.md) owns behavior and the [Knowledge data model](../../../docs/development/data-model.md#knowledge) owns records. Read the relevant current sections and owning decisions rather than every neighboring guide.
