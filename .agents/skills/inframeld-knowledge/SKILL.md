---
name: inframeld-knowledge
description: Explain or review Inframeld source admission, document versions, logical collection membership, upload batches, source sync and deletion. Use for knowledge lifecycle or onboarding upload questions; use Indexing for numerical vector protocols.
---

# Inframeld Knowledge

Explain source information before it becomes searchable. Knowledge owns Documents, immutable DocumentVersions, Collections, exact CollectionRevisions, upload admission, and source synchronization. Indexing owns readiness; Releases owns traffic.

## Scope and reading route

Default to read-only help; loading this skill grants no edit or execution permission. Read only the relevant current section. Report contradictions and distinguish accepted design from code actually inspected.

- [Knowledge lifecycle](../../../docs/development/knowledge-lifecycle.md) owns behavior; [Knowledge records](../../../docs/development/data-model.md#knowledge) defines identities and relationships. [ADR-0008](../../../docs/adr/ADR-0008-preserve-immutable-versions-and-their-provenance.md) explains immutable provenance.
- [Ingestion security](../../../docs/development/ingestion-security.md) covers admission and parsing; [Jobs and idempotency](../../../docs/development/jobs-and-idempotency.md) covers retries; [Retention and deletion](../../../docs/development/retention-and-deletion.md) covers erasure.
- [Onboarding](../../../docs/development/onboarding.md) covers private defaults and first publication. Read [Access control](../../../docs/development/access-control.md) for group/action checks, [Indexing](../../../docs/development/indexing.md) for preparation, and [Deployment](../../../docs/development/deployment.md) for artifact publication only when needed.
- [Maintainer checks](../../../docs/development/knowledge-lifecycle.md#maintainer-checks) summarize the lifecycle scenarios to review.

- For replacement, follow [admission](../../../docs/development/knowledge-lifecycle.md#admission) → [frozen corpus](../../../docs/development/knowledge-lifecycle.md#corpus). For deletion races, read [blocking access before cleanup](../../../docs/development/retention-and-deletion.md#operation).

## Essential boundaries

A Document identifies a logical source; a DocumentVersion identifies immutable bytes. A Collection names a corpus; a CollectionRevision freezes exact versions. Uploaded, admitted, parsed, and searchable are different states. A manifest inventories identities and fingerprints; it is not a permission authority or numerical vector backup. Avoid a class, repository, or aggregate per noun and avoid loading a whole large collection into memory.

Admit bounded supported input through private staging, byte/metadata validation, server-generated storage keys, and complete durable artifact verification. Filenames are display text. Partial upload does not admit a source. Add documents is required on every selected same-project group, including defaults, and the initial allowlist must be nonempty. It does not authorize reading, replacement, deletion, audience changes, or release.

Re-observing authoritative equal content reuses its version; changed bytes create a new one. Names are not stable identity and arbitrary S3 ETags are not content checksums. Update documents is separately required on every group in the persisted current allowlist, with current checks at commit. Preserve source identity and groups; never rewrite old versions.

For R1={A1,B1}, replacing B creates B2 and R2={A1,B2}. R1 remains unchanged. Retained pipelines follow exact versions, not mutable latest values. Indexing can prepare the same admitted source under another profile without another upload; Knowledge cannot declare it ready because upload completed.

Current access protects historical versions, downloads, and citations. Changing a Document’s audience requires a human managing every group in the current or proposed allowlist. Each manager must also have ordinary membership in that same group under the [Access rule](../../../docs/development/access-control.md#group-managers). Reading alone does not permit audience changes. Group deletion is blocked by Document or active upload/source references; it never cascades into document deletion or replacement defaults. Source sync does not import upstream ACLs or grant all project members access. Manual read-only S3 sync preserves approved scope, checkpoints, and source identity; missing observations inform a new revision, not a rewrite of retained releases.

Delete documents is a separate action required for every current group. Deletion covers the Document’s versions: first deny access and publication through a scoped marker, then perform reference-aware resumable cleanup. Late jobs cannot republish it. A corpus omission, audience change, and erasure are different operations; erasure can invalidate retained releases and evidence.

Private onboarding uses ordinary resources and nonempty defaults. Changing upload defaults requires Manage upload defaults plus management of all current/proposed groups; it affects future admissions only, which still require Add documents. Automatic mode cannot turn upload-only rights, a draft, or a partial batch into release authority. A complete authorized batch freezes the full corpus, including unchanged documents. New authorized selections supersede old publication requests; manual mode leaves inputs unpublished. Initial setup needs no benchmark or judge.

## Explain and review

Trace two documents and one replacement, a duplicate upload retry, or deletion during a build. Identify the owner at each step, current permissions, stable identities, and failure outcome. Cite the exact rule, suggest behavior checks when appropriate, and do not introduce a connector framework, event bus, source-ACL platform, or operations programme.
