# ADR-0105: Coordinate exact spending reservations and uncertain settlement

**Status:** Accepted

**Date:** 2026-10-29. The developer explicitly approved all three model-calls, provider-secrets and spending proposals on 2026-10-29 and requested their repository and GitHub documentation. Acceptance selects the contract, not implemented adapters or passing qualification.

## Context and Problem Statement

Alice and Bob can otherwise reserve the same remaining dollar. A lost provider response may still be billed, and later policy edits must not erase costs or release that uncertainty.

## Considered Options

- Share a short transactional accounting boundary for policy, reservations and settlement. Selected.
- Use conditional revision/balance updates with explicit conflicts, requiring careful atomic predicates and no hidden redispatch.

## Decision Outcome

Reserve against all applicable Project and operation limits atomically. Use exact decimals with an initial USD 0.000000000001 quantum and conservative upward reservation/accounting rounding. Preserve captured usage/rate basis and one settlement per call. Unknown holds survive timeout, restart and month changes. Reconciliation requires call-bound evidence and authorized audited correction. Final dispatch authorization checks current policy. Each call keeps its reservation-month attribution, while the operation limit remains cumulative.

The [approved PD-CONTRACTS-02 contract](../../.agents/skills/inframeld-application-contracts/references/decision-spending-coordination.md#approved-resolution) owns exact behavior, examples and qualification cases.

## Consequences

Shared state can contend and unresolved holds can temporarily block work. Unsupported price/usage bounds block capped dispatch. Raising a limit or changing the month does not restart work. Accounting is not an invoice-accuracy guarantee, and no new budget hierarchy is introduced.

Backend implementation, native public schemas and runtime qualification remain separate delivery work.

## Links

- [Stable decision reference](../../.agents/skills/inframeld-application-contracts/references/decision-spending-coordination.md)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
