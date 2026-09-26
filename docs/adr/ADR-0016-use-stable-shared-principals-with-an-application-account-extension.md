# ADR-0016: Use stable shared principals with an application-account extension

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

Human sessions and incoming application keys differ, but duplicating their permission systems would create two interpretations of the same project and action rules.

## Considered Options

- One principal identity model with separate authentication details and a small application-account extension.
- Separate human and application authorization systems.
- An application-only owning-project field mixed into every human principal row.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Use one stable local principal ID with trusted kind and status. Keep verified human identity links and application credentials separate from current permissions. Record an application’s one owning project in application_accounts using the shared principal ID, and enforce that binding in membership relationships. Humans can have explicit memberships in several projects.

**Example.** Replacing SupportBot’s key identifies the same bot. Creating a different bot with the same display name creates a different identity and does not recover old grants.

## Consequences

- Credentials can change without changing identity or duplicating permission semantics, while applications retain a clear project owner.
- Kind, project binding, atomic creation, and retirement require explicit constraints and policy checks. Shared identity does not make applications eligible for human-only administration or allow moving them between projects.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current data model](../development/data-model.md).
- [Current access control](../development/access-control.md).
- Related decisions: [ADR-0012](ADR-0012-use-kratos-for-human-authentication.md), [ADR-0013](ADR-0013-keep-authorization-in-access-and-postgresql.md), [ADR-0014](ADR-0014-bound-permission-delegation-by-action-and-exact-target.md), [ADR-0015](ADR-0015-keep-document-group-access-separate-from-operational-permissions.md), [ADR-0017](ADR-0017-let-valid-application-keys-use-current-account-permissions.md), [ADR-0018](ADR-0018-use-opaque-expiring-and-revocable-application-credentials.md), [ADR-0019](ADR-0019-permit-emergency-suspension-with-scoped-operator-recovery.md), [ADR-0020](ADR-0020-store-current-grants-in-target-specific-relational-tables.md), [ADR-0021](ADR-0021-separate-current-grants-from-transactional-audit-history.md), [ADR-0022](ADR-0022-coordinate-access-writes-by-project-with-scope-revisions.md).
- Delivery boundary: the shared Access foundation establishes common identity, grants, and scoped persistence rules. Human sessions, private defaults, administration and handover, document-access checks, and incoming credentials remain with their owning workflows.
