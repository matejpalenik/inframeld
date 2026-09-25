# ADR-0037: Use controlled migrations and coordinated maintenance upgrades

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

The API and worker share persisted database, job, and artifact formats. Starting a new image does not prove compatibility, and reverting an image does not safely undo changed data.

## Considered Options

- One operator-controlled migration path and coordinated maintenance upgrades.
- Run migrations independently at every API or worker startup.
- Require zero-downtime upgrades and dual-writing for every change.
- Automatically reverse migrations on an image rollback.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Run migrations once through an operator-controlled command or job protected by a database migration lock. Upgrade compatible API and worker versions together during a maintenance window. Startup checks compatibility. Reopen traffic only after the required checks pass; allow application rollback only when the older runtime understands the resulting stored representations.

**Example.** An older worker may not understand a new saved job shape even if an optional database column is harmless to it. Both compatibility questions must be checked.

## Consequences

- Schema changes have one execution owner and upgrades account for persisted work as well as application code.
- Upgrades interrupt service and require handling in-flight work, backups, and verification. Some changes require staged migration or restoration rather than a simple image rollback.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current upgrades and recovery](../development/upgrades-and-recovery.md).
