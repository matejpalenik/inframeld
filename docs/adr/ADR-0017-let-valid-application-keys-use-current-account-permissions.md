# ADR-0017: Let valid application keys use current account permissions

Status: Accepted

**Date:** 2026-09-17

## Context and Problem Statement

An integration’s permissions need to change without replacing every usable credential. Per-key permission ceilings would introduce another layer of scope to administer.

## Considered Options

- Current fine-grained permissions on the application account.
- A fixed permission snapshot or independent ceiling on every key.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Have every valid application key identify its stable application principal and use that account’s current permissions, including later authorized additions and removals. Preserve credential expiry, revocation, audience/resource binding, and adapter restrictions. Use separate application accounts when integrations need different access boundaries.

**Example.** If SupportBot later receives HR access, its existing valid keys receive that access too. Use a different application account when that expansion should not reach the same credential holders.

## Consequences

- One account-level permission model governs active credentials and permission changes do not require key replacement.
- Anyone holding a still-valid key receives later permissions granted to that account. Issuance checks are not a permanent ceiling on existing keys or a live dependency on the issuer’s own rights.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current access control](../development/access-control.md).
- Related decisions: [ADR-0012](ADR-0012-use-kratos-for-human-authentication.md), [ADR-0013](ADR-0013-keep-authorization-in-access-and-postgresql.md), [ADR-0014](ADR-0014-bound-permission-delegation-by-action-and-exact-target.md), [ADR-0015](ADR-0015-keep-document-group-access-separate-from-operational-permissions.md), [ADR-0016](ADR-0016-use-stable-shared-principals-with-an-application-account-extension.md), [ADR-0018](ADR-0018-use-opaque-expiring-and-revocable-application-credentials.md), [ADR-0019](ADR-0019-permit-emergency-suspension-with-scoped-operator-recovery.md), [ADR-0020](ADR-0020-store-current-grants-in-target-specific-relational-tables.md), [ADR-0021](ADR-0021-separate-current-grants-from-transactional-audit-history.md), [ADR-0022](ADR-0022-coordinate-access-writes-by-project-with-scope-revisions.md).
- Delivery boundary: the shared Access foundation establishes common identity, grants, and scoped persistence rules. Human sessions, private defaults, administration and handover, document-access checks, and incoming credentials remain with their owning workflows.
