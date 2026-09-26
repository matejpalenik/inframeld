# ADR-0014: Bound permission delegation by action and exact target

Status: Accepted, with group-manager eligibility partially superseded by [ADR-0049](ADR-0049-require-group-managers-to-be-ordinary-members.md).

**Date:** 2026-09-17

## Context and Problem Statement

An administrator must be able to share the authority they manage without gaining every project resource or creating an escalation path through a broad administrator role.

## Considered Options

- Explicit can-use and can-use-and-grant authority for an exact action and target.
- An unrestricted in-app administrator or wildcard authority over future resources.
- Chains of grantor-dependent permissions that disappear when the original grantor leaves.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

**Current qualification:** an earlier version of this decision permitted group managers without ordinary membership. [ADR-0049](ADR-0049-require-group-managers-to-be-ordinary-members.md), accepted on 25 September 2026, replaces that eligibility rule. Every manager must now have an explicit ordinary membership in the same group. The bounded action grants, peer management, and handover rules remain accepted.

Use the two accepted grant levels and the fixed action catalogue. Humans can receive grant authority; applications can only use eligible actions. Require current authority for the action and exact scope being changed. Keep group management authority separate from ordinary membership: every manager is also a member, but membership alone does not make someone a manager. Enforce ordinary last-manager/grantor handover and explicit creator assignments without an implicit document-read bypass.

**Example.** Alice can grant Manage releases on A without being able to release B. Bob’s grant survives Alice’s departure unless an authorized operation separately removes Bob’s assignment.

## Consequences

- Administration can be delegated in bounded pieces while the same current policy applies to peers and creators.
- Some operations require several current checks and coordinated replacement before departure. A grant’s provenance is not permanent control, and fixed implications such as Edit including View need explicit handling.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current access control](../development/access-control.md).
- [Current data model](../development/data-model.md).
- Related decisions: [ADR-0012](ADR-0012-use-kratos-for-human-authentication.md), [ADR-0013](ADR-0013-keep-authorization-in-access-and-postgresql.md), [ADR-0015](ADR-0015-keep-document-group-access-separate-from-operational-permissions.md), [ADR-0016](ADR-0016-use-stable-shared-principals-with-an-application-account-extension.md), [ADR-0017](ADR-0017-let-valid-application-keys-use-current-account-permissions.md), [ADR-0018](ADR-0018-use-opaque-expiring-and-revocable-application-credentials.md), [ADR-0019](ADR-0019-permit-emergency-suspension-with-scoped-operator-recovery.md), [ADR-0020](ADR-0020-store-current-grants-in-target-specific-relational-tables.md), [ADR-0021](ADR-0021-separate-current-grants-from-transactional-audit-history.md), [ADR-0022](ADR-0022-coordinate-access-writes-by-project-with-scope-revisions.md).
- Delivery boundary: the shared Access foundation establishes common identity, grants, and scoped persistence rules. Human sessions, private defaults, administration and handover, document-access checks, and incoming credentials remain with their owning workflows.
