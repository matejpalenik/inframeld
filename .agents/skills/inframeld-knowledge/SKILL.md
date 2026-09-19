---
name: inframeld-knowledge
description: Explain or review Inframeld source admission, document versions, logical collection membership, upload batches, source sync and deletion. Use for knowledge lifecycle or onboarding upload questions; use Indexing for numerical vector protocols.
---

# Inframeld Knowledge

Help the developer reason about the information the product owns before it
becomes searchable. Knowledge owns source identity, Documents and their immutable
DocumentVersions, logical Collections and exact CollectionRevisions. It does not
own vector readiness, model-provider credentials or Deployment pointers.

## Scope and sources

Default to read-only assistance. Loading this skill grants no edit or execution
permission. Paths below are relative to the repository root. Read the relevant
section of `docs/ARCHITECTURE.md`, then the owning ADR before applying a detailed
rule. Report contradictions; skills are derived guidance, not a second design.

- Start with the guide's first-use, identities and knowledge-ingestion sections.
- Read `docs/adr/ADR-0003-immutable-rag-lineage-and-release-identities.md` for
  source/version/membership identity.
- For uploads and parsing admission, read
  `docs/adr/ADR-0010-secure-document-ingestion-boundary.md`.
- For retries, read `docs/adr/ADR-0007-durable-jobs-idempotency-and-recovery.md`;
  for erasure, `docs/adr/ADR-0014-data-retention-deletion-and-external-processing.md`.
- For default uploads/resources, read
  `docs/adr/ADR-0019-default-onboarding-and-first-publication.md`.
- Read ADR-0005 only when access is at issue, ADR-0015 when passing work to
  Indexing, and ADR-0011 when checking the artifact adapter's publication rules.

## Language and consistency boundaries

A Document identifies a logical source. A DocumentVersion identifies immutable
bytes. A Collection names a corpus; a CollectionRevision freezes exact versions.
An uploaded object, admitted source, parsed artifact and searchable materialization
are distinct states. A manifest inventories identities and fingerprints; it is
not a second permission authority or a reconstruction of numerical vectors.

Document and Collection are the conceptual roots to examine for source and
membership invariants. A version or membership row need not become another
aggregate class. The documents define behavior, not an implemented class/table
map. A large Collection must not require loading its whole corpus into memory.

## Rules that prevent the common mistakes

1. Admit only supported, bounded inputs. Stream into private staging, validate
   bytes and metadata, use server-generated storage keys, and publish a durable
   source reference only after complete artifact upload/verification. A filename
   is display text. Partial upload success is not source admission.
2. Re-observing an authoritative equal content hash reuses the version; changed
   content produces a new one. Preserve logical source identity for replacement.
   Do not claim two equal names identify one source or treat every S3 ETag as a
   content checksum.
3. A collection revision names exact versions. R1={A1,B1}; replacing B produces
   B2 and a new R2={A1,B2}. R1 is unchanged. Never follow mutable latest versions
   from a retained pipeline or mutate Chroma membership arrays.
4. Processing/indexing is delegated through application behavior. Knowledge
   cannot declare a materialization ready because the source upload completed.
   Indexing may reuse the admitted version under different immutable profiles;
   users need not upload the same bytes again.
5. Current group policy protects historical versions, downloads and citations.
   An empty allowlist is not public access. Source sync does not automatically
   import SharePoint/S3 permissions or grant every project member source access.
6. Manual read-only S3 sync uses approved bucket/prefix scope and checkpoints.
   Missing source observations inform a new corpus revision; they do not rewrite
   live or rollback versions. Connector/source identity is stable across retry.
7. Deletion first revokes publication/access under a scoped tombstone, then
   performs bounded reference-aware cleanup. Late jobs cannot publish deleted
   content. Ordinary removal from a new revision differs from explicit erasure
   that can invalidate retained releases. Do not promise immediate physical
   deletion merely because application access is denied.

## Default path and neighboring owners

Configure models → upload → ask without manual internal resource setup is an
accepted v1 requirement. Defaults use ordinary resources and the same admission,
access, profile and build rules. Creator-private provisioning and nonempty
default upload groups are accepted. ADR-0019 selects Automatic updates for the
default path and Manual releases for new deployments unless automatic is chosen
at creation; switching works both ways. An authorized completed batch can request
build and publication for its target in automatic mode. Upload-only permission,
partial admission or a saved draft never unconditionally releases. Each request
freezes a complete corpus; newer authorized selections supersede older pending
publication without dropping unchanged documents. Manual mode leaves new inputs
unpublished. Its shared default-route shape is an implementation recommendation.
Initial model setup does not require a benchmark or judge.

Use Access to determine the actor/project/document scope; Indexing to turn an
admitted revision into verified search data; Pipelines/Releases to bind and serve
it. Read the relevant neighboring ADR rather than load every domain skill.

## Useful review tasks and expected checks

- Explain a two-document upload and one replacement: identify source identity,
  versions, immutable memberships and where readiness is established.
- Review duplicate upload or sync retries: one admitted logical outcome, stable
  identities, no published partial object and no unintended model-call retry.
- Review deletion during a build: tombstone denies later publication, retained
  references are considered, and the user sees honest cleanup status.

Trace success, a retry and one failure relevant to the task. Cite the owning rule,
separate planned behavior from inspected code, and suggest tests of behavior rather
than a test/class per noun. Do not introduce a connector framework, event bus,
source-ACL platform or new operations programme.
