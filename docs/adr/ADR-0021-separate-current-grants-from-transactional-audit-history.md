# ADR-0021: Separate current grants from transactional audit history

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

Authorization needs a clear current assignment set, while administrators need to understand changes. Retaining revoked grants in the current table makes every permission read responsible for excluding them.

## Considered Options

- Current grant rows plus separate audit records committed together.
- Inactive or revoked assignment rows mixed into the current grant set.
- Reconstruct current authority from an event history.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Delete a grant’s current row on revocation and update its level on downgrade. Write the corresponding bounded audit event in the same transaction. Evaluate current assignments with normal eligibility checks, never historical grants. A later regrant is a fresh assignment. Preserve the separate lifecycle behavior of suspension, retired resources, and credential metadata.

**Example.** Revoking SupportBot’s Query row stops Query even while its key remains valid. The retained audit event cannot serve as a fallback permission.

## Consequences

- Current-state queries have one clear assignment set, with an attributable history of authorized changes.
- Audit fields, visibility, retention, and erasure still need their workflow detail. History must not contain secrets or become a permanent content archive. A state change must not commit without its required audit record.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current data model](../development/data-model.md).
- [Current access control](../development/access-control.md).
- [Current retention and deletion](../development/retention-and-deletion.md).
- Related decisions: [ADR-0012](ADR-0012-use-kratos-for-human-authentication.md), [ADR-0013](ADR-0013-keep-authorization-in-access-and-postgresql.md), [ADR-0014](ADR-0014-bound-permission-delegation-by-action-and-exact-target.md), [ADR-0015](ADR-0015-keep-document-group-access-separate-from-operational-permissions.md), [ADR-0016](ADR-0016-use-stable-shared-principals-with-an-application-account-extension.md), [ADR-0017](ADR-0017-let-valid-application-keys-use-current-account-permissions.md), [ADR-0018](ADR-0018-use-opaque-expiring-and-revocable-application-credentials.md), [ADR-0019](ADR-0019-permit-emergency-suspension-with-scoped-operator-recovery.md), [ADR-0020](ADR-0020-store-current-grants-in-target-specific-relational-tables.md), [ADR-0022](ADR-0022-coordinate-access-writes-by-project-with-scope-revisions.md).
- Delivery boundary: the shared Access foundation establishes common identity, grants, and scoped persistence rules. Human sessions, private defaults, administration and handover, document-access checks, and incoming credentials remain with their owning workflows.
