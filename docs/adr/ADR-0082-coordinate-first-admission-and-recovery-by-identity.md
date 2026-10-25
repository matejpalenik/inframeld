# ADR-0082: Coordinate first admission and recovery by identity

**Status:** Accepted design. Identity coordination is not yet implemented.

**Date:** 2026-10-25

## Context and Problem Statement

Alice has a Kratos identity but no local Inframeld account. She accepts Bob's invitation while account recovery begins. Recovery cannot find an organization through an identity link that does not exist yet. Account creation cannot safely check for a recovery block and then create that link independently.

[ADR-0022](ADR-0022-coordinate-access-writes-by-project-with-scope-revisions.md) coordinates existing Access changes through organization and project locks. This decision adds the missing identity-level ordering point without replacing those locks. The developer approved option A and its concrete transaction-lock design to resolve [PD-ACCESS-04](../../.agents/skills/inframeld-access-models/references/decision-recovery-first-admission.md).

## Considered Options

- Give participating operations turns for the same verified provider identity. A transaction-scoped advisory lock works before an account or credential-version row exists. The application must make every participating workflow use the same rule.
- Prepare concurrently and conditionally commit against unchanged identity/recovery observations. This can reduce waiting, but needs additional conflict-detection and retry rules covering absent records and concurrent initialization.

## Decision Outcome

Use one exclusive PostgreSQL transaction-scoped advisory lock derived consistently from the trusted installation, provider authority and subject. The lock requires no account, identity link or credential-version row. It is released when the transaction ends. Its implementation must use a stable namespaced key and exact identity predicates for all record access.

First local admission, recovery admission, recovery completion and credential-state initialization participate. Acquire identity coordination before organization/project locks or credential-state writes. Then acquire any organization/project locks in their existing order and reread current facts before deciding or changing state. Preserve version advancement, initialization protections, unique identity links and atomic invitation consumption.

Provider verification happens outside these transactions. Consent's initializer still closes its short metadata transaction before browser verification. Identity-lock waiting belongs to the operation's bounded database work, with existing five-second recovery deadlines unchanged. The transaction owner rolls back timeout, cancellation and other failures. Unavailable-state handling remains distinct from a recovery conflict.

For a valid new invitation activation, a pending recovery causes a safe 409 without account creation, invitation consumption or assignments. Alice may explicitly try again after recovery. If activation commits first, the later recovery finds the new link and blocks that account. Concurrent activation still uses the original-operation and invitation rules, so it cannot create a duplicate principal or repeat assignments.

The [owning coordination workflow](../../.agents/skills/inframeld-access-models/references/identity-admission-coordination.md) explains the participants and failure boundaries. Ordinary authentication reads and project-grant writes retain their existing behavior. A lock establishes ordering, not identity proof, authority or provider-cleanup confirmation.

## Consequences

- The absent-account case has a common ordering point without provisioning an account or adding a coordination table.
- Organization-before-project ordering remains in force. Participating operations must enter identity coordination first and must not acquire it after taking those locks.
- All participating paths must use the same rule. PostgreSQL does not make an application-defined advisory lock a substitute for constraints or authorization.
- Completion without local admission still creates no account and releases only its eligible original checklist. Credential versions are never reset or downgraded.
- Current adapters, first-admission delivery and concurrency tests still need implementation. This documentation decision adds no code, configuration, migration or runtime evidence.

## Links

- [Resolved PD-ACCESS-04](../../.agents/skills/inframeld-access-models/references/decision-recovery-first-admission.md), [invitation activation](../../.agents/skills/inframeld-access-models/references/admission-and-invitations.md#invitations) and [recovery completion](../../.agents/skills/inframeld-access-models/references/recovery-completion.md#recovery-completion-workflow).
- [ADR-0062: Invitation authority](ADR-0062-activate-invitations-under-current-issuer-authority.md), [ADR-0069: Independent recovery release](ADR-0069-release-completed-recovery-obligations-independently.md) and [ADR-0072: Credential versions](ADR-0072-version-human-cli-credentials-across-account-recovery.md).
- [PostgreSQL 16 advisory-lock behavior](https://www.postgresql.org/docs/16/explicit-locking.html#ADVISORY-LOCKS) and [transaction-scoped lock functions](https://www.postgresql.org/docs/16/functions-admin.html#FUNCTIONS-ADVISORY-LOCKS).
