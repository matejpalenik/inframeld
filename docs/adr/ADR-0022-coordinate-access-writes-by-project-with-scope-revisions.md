# ADR-0022: Coordinate Access writes by project with scope revisions

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

Two individually valid permission changes can violate a shared rule when they race. For example, two remaining managers can each see the other and both leave.

## Considered Options

- Short project-scoped Access transactions coordinated with organization locks and scope revisions.
- Fine-grained resource locks from the outset.
- Serializable transactions with coordinated retry handling.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Use the accepted shared organization-row lock followed by the affected project’s exclusive row lock for participating Access changes. Re-read current policy and handover state, check the required expected revision, apply the change, increment the scope revision, and commit audit together. Installation permission/status changes use the organization’s exclusive lock. All participating mutation paths follow the protocol.

**Example.** A stale form cannot remove a freshly regranted assignment merely because its recipient/action/target tuple looks the same. The scope revision has changed.

## Consequences

- Same-project administration changes have a simple common coordination point, while ordinary changes in different projects can proceed concurrently.
- Same-project writes can wait for one another. Use stable multi-project lock order, bounded waits, and failure handling. Never hold these transactions across uploads, identity-provider calls, model calls, or user waits. The protocol still requires implementation and concurrency tests.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current access control](../development/access-control.md).
- [Current data model](../development/data-model.md).
- Related decisions: [ADR-0012](ADR-0012-use-kratos-for-human-authentication.md), [ADR-0013](ADR-0013-keep-authorization-in-access-and-postgresql.md), [ADR-0014](ADR-0014-bound-permission-delegation-by-action-and-exact-target.md), [ADR-0015](ADR-0015-keep-document-group-access-separate-from-operational-permissions.md), [ADR-0016](ADR-0016-use-stable-shared-principals-with-an-application-account-extension.md), [ADR-0017](ADR-0017-let-valid-application-keys-use-current-account-permissions.md), [ADR-0018](ADR-0018-use-opaque-expiring-and-revocable-application-credentials.md), [ADR-0019](ADR-0019-permit-emergency-suspension-with-scoped-operator-recovery.md), [ADR-0020](ADR-0020-store-current-grants-in-target-specific-relational-tables.md), [ADR-0021](ADR-0021-separate-current-grants-from-transactional-audit-history.md).
- Delivery boundary: the shared Access foundation establishes common identity, grants, and scoped persistence rules. Human sessions, private defaults, administration and handover, document-access checks, and incoming credentials remain with their owning workflows.
