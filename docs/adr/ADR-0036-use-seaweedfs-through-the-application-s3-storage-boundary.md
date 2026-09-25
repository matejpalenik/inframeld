# ADR-0036: Use SeaweedFS through the application S3 storage boundary

Status: Accepted

**Date:** 2026-09-17

## Context and Problem Statement

Documents and processing artifacts need private durable object storage in the single-server installation. Application rules should not depend on a storage vendor’s SDK or expose internal object endpoints.

## Considered Options

- SeaweedFS packaged in the supported deployment behind a small S3 adapter.
- Make an external hosted object store mandatory.
- Let domain code or public callers operate directly on storage internals.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Use the selected SeaweedFS S3 service through ArtifactStore and the documented private adapter boundary. Preserve the single-process packaging, explicit durable paths, bounded artifact operations, publication checks, and complete backup requirements. The application owns object identity and admission; an S3 ETag is not automatically an authoritative content checksum.

**Example.** An uploaded temporary object is not an admitted Document until the application verifies and publishes the durable source reference.

## Consequences

- The installation has an application-owned object-storage boundary without requiring a hosted storage account.
- S3 compatibility, completeness checks, persistence, image selection, and restoration need qualification. SeaweedFS data and metadata both belong to the coordinated recovery set.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current deployment](../development/deployment.md).
- [Current knowledge lifecycle](../development/knowledge-lifecycle.md).
- [Current upgrades and recovery](../development/upgrades-and-recovery.md).
- Related decisions: [ADR-0035](ADR-0035-deploy-v1-on-one-server-through-docker-compose.md).
