# ADR-0018: Use opaque expiring and revocable application credentials

Status: Accepted

**Date:** 2026-09-17

## Context and Problem Statement

Customer applications need incoming authentication independent of human browser sessions. Credential replacement must preserve identity while allowing compromised credentials to be stopped.

## Considered Options

- High-entropy opaque credentials with stored verifiers, safe metadata, expiry, and revocation.
- Treat the secret itself as the application identity or store a reusable plaintext copy for retrieval.
- Unlimited overlapping keys or implicit eviction of an old key during creation.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Use show-once opaque incoming credentials mapped to stable application principals. Store only their verifier and safe metadata, preserve the required bindings, and permit at most two usable keys across audiences. Create the replacement, update consumers, then explicitly revoke the old key. Separate human issuance and revocation permissions; issuance also checks authority to grant all of the application’s current access.

**Example.** A compromised last key may be revoked immediately even if doing so stops the integration. Creating a new key does not automatically delete the old one.

## Consequences

- Credentials can be replaced or immediately revoked without rebuilding the application’s identity and grants.
- Lost plaintext cannot be recovered through replay. Concurrent issuance, deletion, expiry, and grant changes require coordinated checks. Exact credential format, verifier construction, and lifetime limits remain work for the credential feature.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current access control](../development/access-control.md).
- [Current data model](../development/data-model.md).
- [Current jobs and idempotency](../development/jobs-and-idempotency.md).
- Related decisions: [ADR-0012](ADR-0012-use-kratos-for-human-authentication.md), [ADR-0013](ADR-0013-keep-authorization-in-access-and-postgresql.md), [ADR-0014](ADR-0014-bound-permission-delegation-by-action-and-exact-target.md), [ADR-0015](ADR-0015-keep-document-group-access-separate-from-operational-permissions.md), [ADR-0016](ADR-0016-use-stable-shared-principals-with-an-application-account-extension.md), [ADR-0017](ADR-0017-let-valid-application-keys-use-current-account-permissions.md), [ADR-0019](ADR-0019-permit-emergency-suspension-with-scoped-operator-recovery.md), [ADR-0020](ADR-0020-store-current-grants-in-target-specific-relational-tables.md), [ADR-0021](ADR-0021-separate-current-grants-from-transactional-audit-history.md), [ADR-0022](ADR-0022-coordinate-access-writes-by-project-with-scope-revisions.md).
- Delivery boundary: the shared Access foundation establishes common identity, grants, and scoped persistence rules. Human sessions, private defaults, administration and handover, document-access checks, and incoming credentials remain with their owning workflows.
