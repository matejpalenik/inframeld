# ADR-0019: Permit emergency suspension with scoped operator recovery

Status: Accepted

**Date:** 2026-09-17

## Context and Problem Statement

A compromised human must be blocked even when that person is the only manager. Ordinary departure and emergency containment cannot have the same replacement requirement.

## Considered Options

- Immediate suspension retaining assignments, with deliberate identity recovery or narrow operator replacement.
- Refuse suspension of the last manager.
- Give ordinary in-app administrators unrestricted account takeover or document access.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Allow authorized emergency suspension without last-manager handover. Preserve recorded assignments while blocking the principal. Restore the same legitimate identity only after the required security checks; password reset alone is insufficient. If authority is stranded, privileged operator maintenance may install a verified replacement for the exact group or missing action/scope, recording actor, reason, and change.

**Example.** Suspend the only Support manager to stop a compromise. Keep that account blocked while scoped maintenance appoints a verified replacement; do not make every installation administrator a Support reader.

## Consequences

- Containment can happen immediately without accepting that a stranded group is permanently unrecoverable.
- The server operator is inside the infrastructure trust boundary. Audit does not remove that trust, and ordinary application sessions still obey their explicit grants. Recovery must not revive removed permissions.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current access control](../development/access-control.md).
- [Current upgrades and recovery](../development/upgrades-and-recovery.md).
- [ADR-0049](ADR-0049-require-group-managers-to-be-ordinary-members.md) requires both ordinary membership and management for a replacement group manager. Emergency suspension still blocks both immediately.
- Related decisions: [ADR-0012](ADR-0012-use-kratos-for-human-authentication.md), [ADR-0013](ADR-0013-keep-authorization-in-access-and-postgresql.md), [ADR-0014](ADR-0014-bound-permission-delegation-by-action-and-exact-target.md), [ADR-0015](ADR-0015-keep-document-group-access-separate-from-operational-permissions.md), [ADR-0016](ADR-0016-use-stable-shared-principals-with-an-application-account-extension.md), [ADR-0017](ADR-0017-let-valid-application-keys-use-current-account-permissions.md), [ADR-0018](ADR-0018-use-opaque-expiring-and-revocable-application-credentials.md), [ADR-0020](ADR-0020-store-current-grants-in-target-specific-relational-tables.md), [ADR-0021](ADR-0021-separate-current-grants-from-transactional-audit-history.md), [ADR-0022](ADR-0022-coordinate-access-writes-by-project-with-scope-revisions.md).
- Delivery boundary: the shared Access foundation establishes common identity, grants, and scoped persistence rules. Human sessions, private defaults, administration and handover, document-access checks, and incoming credentials remain with their owning workflows.
