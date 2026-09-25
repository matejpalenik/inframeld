# ADR-0015: Keep document-group access separate from operational permissions

Status: Accepted

**Date:** 2026-09-17

## Context and Problem Statement

Permission to run a pipeline does not mean permission to read every source in the project. Historical versions, citations, receipts, and evaluation evidence need the same current content boundary.

## Considered Options

- Project-local group allowlists with current evidence checks.
- Implicit document access from project membership, administrator status, or Query alone.
- Caller-supplied group claims or global retrieval followed only by filtering output.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Keep authoritative nonempty Document allowlists and group relationships in PostgreSQL. Operational action checks and document scope remain separate. Apply current policy to all protected evidence, including historical versions and uncited sources used in generation. Keep the accepted distinct rules for initial admission, replacement, deletion, and human-controlled audience changes.

**Example.** SupportBot may query A while seeing Support documents only. Removing its Support group membership removes that audience even if its Query grant remains.

## Consequences

- A permitted operation can use only the evidence currently permitted to its acting principal.
- Every retrieval, history, dispatch, and disclosure path must preserve the boundary. A shared collection, group manager assignment, or resource grant is not an ordinary read bypass.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current access control](../development/access-control.md).
- [Current knowledge lifecycle](../development/knowledge-lifecycle.md).
- [Current data model](../development/data-model.md).
- [ADR-0049](ADR-0049-require-group-managers-to-be-ordinary-members.md) requires explicit membership for every group manager. Reading still uses ordinary membership checks.
- Related decisions: [ADR-0012](ADR-0012-use-kratos-for-human-authentication.md), [ADR-0013](ADR-0013-keep-authorization-in-access-and-postgresql.md), [ADR-0014](ADR-0014-bound-permission-delegation-by-action-and-exact-target.md), [ADR-0016](ADR-0016-use-stable-shared-principals-with-an-application-account-extension.md), [ADR-0017](ADR-0017-let-valid-application-keys-use-current-account-permissions.md), [ADR-0018](ADR-0018-use-opaque-expiring-and-revocable-application-credentials.md), [ADR-0019](ADR-0019-permit-emergency-suspension-with-scoped-operator-recovery.md), [ADR-0020](ADR-0020-store-current-grants-in-target-specific-relational-tables.md), [ADR-0021](ADR-0021-separate-current-grants-from-transactional-audit-history.md), [ADR-0022](ADR-0022-coordinate-access-writes-by-project-with-scope-revisions.md).
- Delivery boundary: the shared Access foundation establishes common identity, grants, and scoped persistence rules. Human sessions, private defaults, administration and handover, document-access checks, and incoming credentials remain with their owning workflows.
