# ADR-0013: Keep authorization in Access and PostgreSQL

Status: Accepted

**Date:** 2026-09-17

## Context and Problem Statement

The accepted model has explicit project and resource grants plus operation-specific rules such as handover and safe key issuance. Another permission engine would not remove those application invariants.

## Considered Options

- Application-owned policy with PostgreSQL relationships and transactions.
- OpenFGA as a dedicated authorization service.
- An embedded general policy library such as PyCasbin.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Retain the Access module as the shared authorization owner and PostgreSQL as the authority for current relationships. Use deny-by-default checks, scoped foreign keys, current status/membership checks, and bounded queries. HTTP, MCP, and workers reuse the application policy. Do not add a generic policy language, speculative engine adapter, or permission cache without a demonstrated need.

**Example.** Reconsider an engine for real deep inheritance, independently deployed applications sharing policy, or measured workload needs—not merely because there are more documents.

## Consequences

- Relevant state and audit changes can share the existing database transaction without another runtime service or policy representation.
- The application must implement and test its permission and concurrency rules. The decision claims no capacity benchmark and does not claim that engines lack the ability to represent these relationships.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current access control](../development/access-control.md).
- [Current data model](../development/data-model.md).
- Related decisions: [ADR-0012](ADR-0012-use-kratos-for-human-authentication.md), [ADR-0014](ADR-0014-bound-permission-delegation-by-action-and-exact-target.md), [ADR-0015](ADR-0015-keep-document-group-access-separate-from-operational-permissions.md), [ADR-0016](ADR-0016-use-stable-shared-principals-with-an-application-account-extension.md), [ADR-0017](ADR-0017-let-valid-application-keys-use-current-account-permissions.md), [ADR-0018](ADR-0018-use-opaque-expiring-and-revocable-application-credentials.md), [ADR-0019](ADR-0019-permit-emergency-suspension-with-scoped-operator-recovery.md), [ADR-0020](ADR-0020-store-current-grants-in-target-specific-relational-tables.md), [ADR-0021](ADR-0021-separate-current-grants-from-transactional-audit-history.md), [ADR-0022](ADR-0022-coordinate-access-writes-by-project-with-scope-revisions.md).
- Delivery boundary: the shared Access foundation establishes common identity, grants, and scoped persistence rules. Human sessions, private defaults, administration and handover, document-access checks, and incoming credentials remain with their owning workflows.
