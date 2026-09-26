# ADR-0020: Store current grants in target-specific relational tables

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

Permissions need exact recipient, action, target, and owning-scope relationships. An unchecked resource-type/ID pair cannot prove that a referenced resource belongs to the project.

## Considered Options

- Separate relational grant tables by target type with scoped foreign keys.
- One authoritative JSON permission document per account.
- One grant table with optional target columns.
- A generic unverified resource registry.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Use one grant table for each supported target type, sharing the application permission model. Enforce one current recipient/action/target assignment and required can_grant boolean; false is use-only, never an explicit deny. Keep supported actions and recipient eligibility in code. Introduce resource-specific tables with their real owning features, not placeholder domain resources.

**Example.** Query and Manage releases on Deployment A share the Deployment-grants table as different actions. A Support grant cannot reference a Finance Deployment.

## Consequences

- Database constraints can reject duplicate and cross-scope relationships while each target type has a real reference.
- Tables do not replace current actor, membership, kind, or handover checks. Separate persistence tables do not require a separate repository, service, or policy algorithm for every target.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current data model](../development/data-model.md).
- [Current access control](../development/access-control.md).
- Related decisions: [ADR-0012](ADR-0012-use-kratos-for-human-authentication.md), [ADR-0013](ADR-0013-keep-authorization-in-access-and-postgresql.md), [ADR-0014](ADR-0014-bound-permission-delegation-by-action-and-exact-target.md), [ADR-0015](ADR-0015-keep-document-group-access-separate-from-operational-permissions.md), [ADR-0016](ADR-0016-use-stable-shared-principals-with-an-application-account-extension.md), [ADR-0017](ADR-0017-let-valid-application-keys-use-current-account-permissions.md), [ADR-0018](ADR-0018-use-opaque-expiring-and-revocable-application-credentials.md), [ADR-0019](ADR-0019-permit-emergency-suspension-with-scoped-operator-recovery.md), [ADR-0021](ADR-0021-separate-current-grants-from-transactional-audit-history.md), [ADR-0022](ADR-0022-coordinate-access-writes-by-project-with-scope-revisions.md).
- Delivery boundary: the shared Access foundation establishes common identity, grants, and scoped persistence rules. Human sessions, private defaults, administration and handover, document-access checks, and incoming credentials remain with their owning workflows.
