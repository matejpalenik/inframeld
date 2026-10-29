# ADR-0100: Order key revocation at protected boundaries

**Status:** Accepted

**Date:** 2026-10-29. The developer explicitly approved all three permissions-and-jobs proposals on 2026-10-29 and requested repository and GitHub documentation. Acceptance selects the policy, not implemented behavior or passing qualification.

## Context and Problem Statement

A key may be revoked between verification and a protected write. Earlier identity evidence cannot establish current authority.

## Considered Options

- Coordinate revocation and protected writes in the existing transaction. Selected.
- Use versioned observations with conditional final checks, requiring every participant to honor the same boundary.

## Decision Outcome

Use fresh stored key/account facts at protected boundaries and transaction-scoped database ordering against revocation for local writes. Check expiry using current database time after coordination waits. Authorize bounded reads, replay and remote dispatch at their documented boundaries. Never hold SQL locks during provider waits or claim that revocation recalls already sent work.

The [approved PD-ACCESS-01 contract](../../.agents/skills/inframeld-access-models/references/decision-key-currentness.md#approved-resolution) owns the complete behavior and examples.

## Consequences

Short coordination adds reads and contention. The current account, exact action and source checks remain mandatory. Known rollback and uncertain commit retain their existing different outcomes.

Implementation, tests and production qualification remain separate delivery work. No application code or public schema is delivered by this documentation decision.

## Links

- [Stable decision reference](../../.agents/skills/inframeld-access-models/references/decision-key-currentness.md)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
