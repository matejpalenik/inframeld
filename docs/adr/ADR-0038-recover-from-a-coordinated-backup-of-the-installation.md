# ADR-0038: Recover from a coordinated backup of the installation

Status: Accepted — operating baseline remains provisional and requires qualification

**Date:** 2026-09-24

## Context and Problem Statement

PostgreSQL, Kratos data, objects, numerical indexes, configuration, and keys refer to one another. Restoring one store alone can leave broken references or silently restore obsolete permissions.

## Considered Options

- A coordinated complete backup and restricted, validated restoration.
- Copy live stores independently or back up only selected components.
- Require distributed recovery machinery or reconstruct every historical index from source.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Require documented and tested backup/restore for production. Retain the recorded daily cold-backup sequence as a provisional operating baseline: stop writers, copy a consistent installation to private staging, restart service, then encrypt and transfer the frozen copy off-host. Restore privately and reconcile later security and deletion changes before reopening safe scopes. Product-level index reconstruction remains deferred.

**Example.** Yesterday’s backup may contain a key revoked today. Restoring the backup must not make that key usable again merely because its old row returned.

## Consequences

- Recovery accounts for the relationships and secrets needed to make the installation usable.
- The procedure and numerical targets still need qualification. A completed local copy is not a completed off-host backup. Lost idempotency history and uncertain external work limit safe replay.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current upgrades and recovery](../development/upgrades-and-recovery.md).
- [Current retention and deletion](../development/retention-and-deletion.md).
