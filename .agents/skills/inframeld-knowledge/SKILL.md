---
name: inframeld-knowledge
description: Explains and reviews Inframeld documents, immutable versions, collections, uploads, source sync and deletion. Use for knowledge lifecycle and upload onboarding, rather than numerical index protocols.
---

# Inframeld Knowledge

Explain how source information becomes admitted product knowledge. Knowledge owns source identity, Documents, immutable DocumentVersions, Collections, exact CollectionRevisions, upload admission and source synchronization. Indexing owns verified search readiness. Releases owns publication.

## Working model

Alice uploads two Support documents, A1 and B1. A Document is the stable identity of a logical source. A DocumentVersion identifies the immutable bytes observed for it.

A Collection groups documents. A CollectionRevision freezes exact versions, forming a corpus, the source material selected for an operation.

If Alice admits replacement B2, the earlier R1={A1,B1} does not change. Only a separately authorized selection can create R2={A1,B2}. That lets a retained query explain which source version it used. Replacing a source, removing it from a new corpus and erasing its history are different operations.

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
5. Cite the owning rule and distinguish design from implementation. Surface conflicts.

For backend component design, code generation or structural review, read [module architecture](references/architecture.md), the affected workflow and Coding Standards. Behavior-only questions go directly to their workflow. Pending proposals do not authorize dependent code.

## Pending decisions for affected work

Load only matching triggers. Discuss and obtain approval before code depends on an unresolved choice, following [decision finalization](../../../docs/development/guides/architecture-decisions.md). Unrelated decisions do not block work. Qualification gaps gate claims, not evidence-gathering tests.

- [PD-KNOWLEDGE-02](references/decision-retention-erasure-policy.md): Before implementing retention configuration, bounded history storage, expiry or cross-domain source-erasure cleanup.

## Accepted decision references

Apply these approved contracts without reopening them. Implementation and qualification remain separate.

- [PD-KNOWLEDGE-01](references/decision-complete-batch-handoff.md): Before implementing batch completion, collection selection, parent/child recovery or the ingestion-to-automatic-update handoff.

## Read as needed

Choose the row matching the task. Workflow, contract and architecture views are separate reading units. Do not load this whole table.

| Task | Direct reference |
| --- | --- |
| Module/component design or structural review | [Knowledge architecture: preserve which source version was accepted](references/architecture.md) |
| Collection selection and batches | [Select a complete corpus after admission](references/collection-selection-and-batches.md) |
| Decision retention erasure policy | [PD-KNOWLEDGE-02: Choose bounded retention without weakening explicit erasure](references/decision-retention-erasure-policy.md) |
| Deletion and retention | [Sharing, deletion and retained evidence](references/deletion-and-retention.md) |
| Documents and collections | [Documents, collections and frozen inputs](references/documents-and-collections.md) |
| Project deletion | [Block a Project and finish its original deletion](references/project-deletion.md) |
| Logical records and representation ownership | [Knowledge identities and relationships](references/records.md) |
| Retention and pins | [Expire retained data without confusing erasure](references/retention-and-pins.md) |
| Source configuration and credentials | [Source configuration, audiences and credentials](references/source-configuration-and-credentials.md) |
| Uploads and source sync | [Uploads, replacement and bounded source sync](references/uploads-and-source-sync.md) |

## Source ownership

Focused references own accepted behavior and logical design. Code, generated OpenAPI and migrations own implemented representations. Read exact definitions when fields matter, ADRs for rationale or conflicts, and matching pending decisions before dependent design. Human guides own development procedures.
