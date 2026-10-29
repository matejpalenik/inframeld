# PD-CONTRACTS-02: Coordinate budget policy, reservations and uncertain settlement

**Status:** ACCEPTED on 2026-10-29 in [ADR-0105](../../../../docs/adr/ADR-0105-coordinate-exact-spending-reservations-and-uncertain-settlement.md). Implementation and qualification remain pending.

**Owner:** `inframeld-application-contracts`

**Issue kind:** Implementation and accounting contract.

The developer explicitly approved all three model-calls, provider-secrets and spending proposals on 2026-10-29 and requested their repository and GitHub documentation. Acceptance selects the contract, not implemented adapters or passing qualification.

## Contents

- [Problem and example](#problem-and-example)
- [Accepted context and evidence](#accepted-context-and-evidence)
- [Alternatives and trade-offs](#alternatives-and-trade-offs)
- [Approved resolution](#approved-resolution)
- [Decision trigger and stopping boundary](#decision-trigger-and-stopping-boundary)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Implementation and required evidence](#implementation-and-required-evidence)
- [Sources and finalization](#sources-and-finalization)

## Problem and example

Alice lowers a monthly limit while two workers reserve model calls. One call times out after it may have been billed. Bob raises the limit later. The update must not erase consumed spending, free an unknown hold or restart the failed work automatically.

The spending rules are accepted. The original analysis identified policy/reservation concurrency, conservative bounds and ledger/recovery contracts as unfinished. The approved resolution below now selects their logical contract, with implementation and evidence still pending. Independent “remaining budget” reads can let concurrent calls spend the same allowance.

## Accepted context and evidence

Reserve against all applicable limits in one short transaction before dispatch. Count settled amounts and unresolved holds. Use fixed-precision decimal arithmetic and captured rates. Close SQL work before provider calls. Missing conservative pricing/bounds blocks capped work, while uncapped unknown pricing remains explicitly disclosed.

Humans need exact project authority to change budgets. Applications cannot raise or remove their controls. Policy changes preserve the ledger, old holds and each call's original reservation month. Operation limits remain cumulative across months. No operation auto-resumes because a month or limit changed. Account/user/connection/organization budget hierarchies remain deferred.

## Alternatives and trade-offs

These preserve the options considered before approval. The approved resolution below owns the selected contract.

1. **Serialize policy and reservations through shared project accounting state.** Use short coordinated transactions and a fixed lock order. This gives clear ordering, but concurrent model work can contend on the shared state.
2. **Use conditional revision/balance updates with explicit conflicts.** Reserve only when the checked state still matches and return the defined conflict when it changes. This option does not authorize automatic transaction or model retries. This can reduce lock duration, but requires careful atomic predicates and cannot redispatch model work.

## Approved resolution

Use one short transactional accounting boundary for the Project and operation limits applicable to a call. Policy changes, reservations and settlement share the same documented coordination order. Record a unique call identity, captured policy/rate basis, conservative reservation and its Project period. Do not hold SQL transactions while waiting for a provider.

Use exact decimal arithmetic. The initial accounting quantum is USD 0.000000000001 (twelve fractional decimal places). Round conservative reservations upward at that quantum. Compute normalized observed costs from trustworthy usage and the captured rates, retain their basis, and conservatively round the accounting debit upward at the same quantum. Display rounding must never drive allowance checks. Keep input/rate precision sufficient to prove the bound, and fail visibly rather than truncate or overflow. These are accounting values, not a promise that the provider invoice uses this rounding.

The qualified adapter must cover all supported billable input, output, reasoning, cache and other categories actually used. Cap output explicitly. Unsupported or unbounded billable behavior, unknown pricing or unavailable accounting blocks a capped call. Estimates are separate from conservative reservations. Without a monetary cap, supported authorized calls can proceed with explicitly unknown pricing. A model name or caller-supplied zero rate never proves free execution.

Check settled spending plus unresolved holds against every applicable limit atomically. Two simultaneous calls cannot both reserve the same final allowance. Keep one idempotent settlement per call, coordinating late observations without double-counting. Release unused reservation only after trustworthy settlement, or release a proven not-sent/not-billed call under its qualified outcome mapping.

Timeout, restart, cancellation, missing usage, elapsed time and a new month do not prove zero cost. Unknown holds remain. Reconciliation needs authoritative call-bound usage/charge evidence, or evidence the request was not sent/billed. Keep evidence, revision checks and an audit record. An authorized human with the existing budget-management permission can resolve an evidence-backed correction, but there is no arbitrary 'mark free' button. Without evidence the hold stays. The human may explicitly change policy while acknowledging the unresolved amount.

Policy edits preserve settled costs, original holds and cumulative operation limits. A lower limit can leave available allowance negative and prevents new calls that do not fit. Final authorization before a bounded dispatch rechecks the current policy and usable pricing/bound. A reserved but not-yet-authorized call that no longer fits must not send, and may release its proven unused hold. Once dispatch authorization has committed, the call is in flight for ordering purposes and cannot be recalled by a later policy edit. No database/network atomicity is claimed.

Each call captures its UTC calendar month at reservation. Late settlement stays in that captured Project month. Calls reserved in a later month use that later Project period, while the original operation's cumulative limit spans them all. Known overages are recorded honestly and stop further affected spending until admissible policy/pricing and evidence resolve the condition. Raising a limit or starting a new month never automatically resumes stopped work or repeats a call.

Expose a permitted typed accounting projection: optional policy/revision, UTC period, settled total, unresolved holds, remaining allowance including a negative value, pricing provenance and the original operation's partial/uncertain state. Include no raw prompts or secrets. Preserve existing human-only policy mutation and separate inspection authority. Add no account/user/connection budget hierarchy.

## Decision trigger and stopping boundary

Apply this accepted contract when the implementation reaches its original trigger. Concrete method names and physical representations remain ordinary implementation choices. Qualification limits support and release claims, not authorized evidence gathering. Discuss a new policy choice only if it would change this approved contract.

## Architectural impact and dependencies

Shared gateway/accounting, Access budget authority, Evaluation/operation limits, imports and CLI inspection. Update reserve/dispatch/settle and concurrent-policy sequences with the same semantics.

Load neighboring decisions only under these conditions:

- [PD-CONTRACTS-01: Enforce model policy on the actual outbound path](decision-gateway-enforcement.md). For actual dispatch/usage mapping.
- [PD-CONTRACTS-04 (accepted): Bind import review and partial recovery to exact actions](decision-import-review-and-recovery.md). When import explicitly applies a budget change.

## Implementation and required evidence

These are required cases and evidence, not recorded passing tests.

Competing reservations/edits, the last available allowance, rounding at the accounting quantum, concurrent duplicate settlement, missing usage, late evidence, period changes, lower limits below existing costs, unsupported price bounds, uncapped unknown pricing and explicit continuation. Prove actual supported bounds without claiming invoice-level accuracy.

## Sources and finalization

- [Spending admission](spending-and-accounting.md#spending).
- [Human-only policy coordination](spending-and-accounting.md#budget-policy-authority).
- [Supporting records](components-and-services.md#shared-supporting-records).

[ADR-0105](../../../../docs/adr/ADR-0105-coordinate-exact-spending-reservations-and-uncertain-settlement.md) records the approval and rationale. Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later policy change. This documentation approval does not authorize application implementation or claim successful qualification.
