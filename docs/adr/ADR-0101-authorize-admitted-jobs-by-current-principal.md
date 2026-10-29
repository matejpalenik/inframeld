# ADR-0101: Authorize admitted jobs by current principal

**Status:** Accepted

**Date:** 2026-10-29. The developer explicitly approved all three permissions-and-jobs proposals on 2026-10-29 and requested repository and GitHub documentation. Acceptance selects the policy, not implemented behavior or passing qualification.

## Context and Problem Statement

Alice starts a long evaluation and her token expires. Coupling every background step to that token would interrupt legitimate work. A compromised key also requires explicit containment behavior.

## Considered Options

- Use current principal authority after durable admission. Selected.
- Require the original credential to remain valid, interrupting work on routine expiry/rotation.
- Ignore expiry but stop on individual key revocation, adding distinct continuation/binding rules.

## Decision Outcome

Accepted product jobs use their original principal, installation, scope and fixed inputs, with current account/resource authority at protected steps. Expiry, replacement and individual key revocation do not automatically cancel admitted work. Revocation blocks new incoming requests. Cancellation or suspension contains existing work. Human recovery-generation changes prevent further protected work until eligible explicit continuation. System recovery/erasure keeps its narrow trusted obligations.

The [approved PD-ACCESS-02 contract](../../.agents/skills/inframeld-access-models/references/decision-admitted-work-authority.md#approved-resolution) owns the complete behavior and examples.

## Consequences

Operators must distinguish revoking a credential from stopping admitted jobs. Workers retain no raw tokens and must use server-owned admission evidence instead of forged incoming authentication. Restored permissions do not automatically restart stopped work. Unknown paid effects cannot be replayed.

Implementation, tests and production qualification remain separate delivery work. No application code or public schema is delivered by this documentation decision.

## Links

- [Stable decision reference](../../.agents/skills/inframeld-access-models/references/decision-admitted-work-authority.md)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
