# PD-CONTRACTS-02: Coordinate budget policy, reservations and uncertain settlement

**Status:** PENDING

**Owner:** `inframeld-application-contracts`

**Issue kind:** Implementation and accounting contract.

This reference supports a future discussion. Its recommendation is not accepted behavior. Current guides and ADRs retain authority.

## Contents

- [Problem and example](#problem-and-example)
- [Accepted context and evidence](#accepted-context-and-evidence)
- [Alternatives and trade-offs](#alternatives-and-trade-offs)
- [Non-binding recommendation](#non-binding-recommendation)
- [Decision trigger and stopping boundary](#decision-trigger-and-stopping-boundary)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Open questions and required evidence](#open-questions-and-required-evidence)
- [Sources and finalization](#sources-and-finalization)

## Problem and example

Alice lowers a monthly limit while two workers reserve model calls. One call times out after it may have been billed. Bob raises the limit later. The update must not erase consumed spending, free an unknown hold or restart the failed work automatically.

The spending rules are accepted. Exact policy/reservation concurrency, conservative pricing/token bounds, ledger/result representations and recovery contracts still need definition. Independent “remaining budget” reads can let concurrent calls spend the same allowance.

## Accepted context and evidence

Reserve against all applicable limits in one short transaction before dispatch. Count settled amounts and unresolved holds. Use fixed-precision decimal arithmetic and captured rates. Close SQL work before provider calls. Missing conservative pricing/bounds blocks capped work, while uncapped unknown pricing remains explicitly disclosed.

Humans need exact project authority to change budgets. Applications cannot raise or remove their controls. Policy changes preserve the ledger, old holds and original admission period. No operation auto-resumes because a month or limit changed. Account/user/connection/organization budget hierarchies remain deferred.

## Alternatives and trade-offs

1. **Serialize policy and reservations through shared project accounting state.** Use short coordinated transactions and a fixed lock order. This gives clear ordering, but concurrent model work can contend on the shared state.
2. **Use conditional revision/balance updates with explicit conflicts.** Reserve only when the checked state still matches and return the defined conflict when it changes. This option does not authorize automatic transaction or model retries. This can reduce lock duration, but requires careful atomic predicates and cannot redispatch model work.

## Non-binding recommendation

**Proposal only.** Prefer a small transactional accounting model shared by policy mutation and reservation, with a reviewed fixed-precision rounding and usage contract. Choose lock/conditional mechanics from concurrent fixtures. Do not infer invoice accuracy or a supported cap from estimates.

## Decision trigger and stopping boundary

Before implementing budget mutation, reservation, settlement, usage normalization or unknown-charge recovery.

Pause unresolved accounting/coordination contracts. Capped production claims require qualified conservative bounds and failure evidence.

## Architectural impact and dependencies

Shared gateway/accounting, Access budget authority, Evaluation/operation limits, imports and CLI inspection. Update reserve/dispatch/settle and concurrent-policy sequences with the same semantics.

Load neighboring decisions only under these conditions:

- [PD-CONTRACTS-01: Enforce model policy on the actual outbound path](decision-gateway-enforcement.md). For actual dispatch/usage mapping.
- [PD-CONTRACTS-04: Bind import review and partial recovery to exact actions](decision-import-review-and-recovery.md). When import explicitly applies a budget change.

## Open questions and required evidence

- Which billable categories and adapter transformations enter the conservative bound?
- How do limit edits order against reservations?
- How is exactly-once local settlement distinguished from uncertain provider charging?
- What authorized evidence resolves a hold or overage?
- Which safe projections expose pricing, periods and partial work?

## Sources and finalization

- [Spending admission](spending-and-accounting.md#spending).
- [Human-only policy coordination](spending-and-accounting.md#budget-policy-authority).
- [Supporting records](components-and-services.md#shared-supporting-records).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
