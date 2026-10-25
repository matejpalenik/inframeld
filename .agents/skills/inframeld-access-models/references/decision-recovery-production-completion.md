# PD-ACCESS-03: Prove recovery cleanup before releasing product access

**Status:** PENDING for the remaining implementation contract. The hook-based approach, Hydra retry limits and explicit operator continuation were accepted on 2026-10-25 in [ADR-0081](../../../../docs/adr/ADR-0081-use-native-kratos-hooks-for-recovery-evidence.md), [ADR-0083](../../../../docs/adr/ADR-0083-bound-hydra-recovery-cleanup-retries.md) and [ADR-0084](../../../../docs/adr/ADR-0084-authorize-additional-recovery-cleanup-runs-through-host-maintenance.md).

**Owner:** `inframeld-access-models`

**Issue kind:** Implementation contract and production qualification.

The approved hook, retry-budget, operator-continuation and failure-handling choices below are accepted design. The remaining questions are unresolved and do not authorize dependent production wiring. Current owning references and ADRs retain authority.

## Contents

- [Problem and example](#problem-and-example)
- [Accepted context and evidence](#accepted-context-and-evidence)
- [Alternatives and trade-offs](#alternatives-and-trade-offs)
- [Accepted hook choice](#accepted-hook-choice)
- [Accepted Hydra retry limits](#accepted-hydra-retry-limits)
- [Accepted operator continuation](#accepted-operator-continuation)
- [Accepted failure handling](#accepted-failure-handling)
- [Decision trigger and stopping boundary](#decision-trigger-and-stopping-boundary)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Open questions and required evidence](#open-questions-and-required-evidence)
- [Sources and finalization](#sources-and-finalization)

## Problem and example

Alice resets her password. Kratos accepts a recovery code before her new password is saved. Meanwhile an older CLI consent or refresh may complete. Two successful Hydra cleanup responses do not by themselves prove that password replacement, session cleanup and all required CLI invalidation are complete. Releasing Alice’s block too early would reopen product access on incomplete evidence.

The integration shape is accepted, but production has not wired the complete trusted evidence and reconciliation path. The internal completion service accepts provider outcomes from its caller. That caller must establish what the outcomes mean. An authenticated generic webhook proves its sender, not that every cleanup obligation has succeeded.

## Accepted context and evidence

Preserve authenticated original-flow registration, native Kratos cleanup, independent durable Hydra cleanup and the product block during the password-setting gap. Private callbacks retain their dedicated rotatable secret, five-field allowlisted bounded body and original-flow/event/phase deduplication. The local aggregate and completion service already implement a subset.

Credential generations prevent stale human CLI credentials from becoming valid again inside Inframeld. They do not prove Hydra cleanup or legitimate-session preservation. Each original recovery releases only its own obligation. Provider calls remain outside SQL transactions. Delayed bulk cleanup can invalidate newer credentials, as already accepted.

## Alternatives and trade-offs

1. **Complete from trusted native events plus durable reconciliation. Selected.** Bind authenticated callbacks to the registered flow and verify their required meaning, then reconcile unfinished independent cleanup. This provides prompt progress when callbacks arrive, but demands careful event ordering and trustworthy native completion evidence.
2. **Require an explicit private completion verification step. Not selected as the default integration.** Treat callbacks as observations and perform a bounded trusted confirmation before recording aggregate provider completion. This adds a private integration step and cannot rely on ordinary generic webhook success.

<a id="non-binding-recommendation"></a>

## Accepted hook choice

On 2026-10-25, the developer approved native hooks after verification against Ory documentation and the pinned v26.2.0 source. [ADR-0081](../../../../docs/adr/ADR-0081-use-native-kratos-hooks-for-recovery-evidence.md) records the scope. The recovery hook admits the obligation after code verification. A password-settings webhook after persistence and native `revoke_active_sessions` supplies the later Kratos evidence, bound to the original recovery. Inframeld then performs independent Hydra cleanup and records its outcomes. No single webhook certifies the whole recovery.

[The private handoff](private-recovery-handoff.md#native-hook-evidence) owns the accepted sequence. Original-flow validation and delivery/reconciliation details still need concrete design. Keep callback authentication separate from evidence qualification. Credential generations do not replace provider cleanup, and this approval does not establish production implementation or runtime qualification.

## Accepted Hydra retry limits

On 2026-10-25, the developer selected a one-hour automatic retry maximum and twelve cleanup attempts, including the initial attempt, for the original recovery operation's initial run. [ADR-0083](../../../../docs/adr/ADR-0083-bound-hydra-recovery-cleanup-retries.md) records the narrow exception to the shared three-attempt rule. The [Access-owned policy](recovery-completion.md#hydra-cleanup-retry-budget) defines eligibility, preserved progress and exhaustion behavior.

Trusted Kratos completion must first make Hydra cleanup eligible. Restarts and duplicate callbacks cannot reset the original deadline or count. Retry only unfinished cleanup with progressively longer waits. Reaching either limit stops new automatic attempts and keeps the recovery block pending operator attention. Already-dispatched calls retain their existing uncertainty rules. Other jobs keep their existing attempt limit.

## Accepted operator continuation

On 2026-10-25, the developer selected another bounded run rather than one extra attempt per approval. [ADR-0084](../../../../docs/adr/ADR-0084-authorize-additional-recovery-cleanup-runs-through-host-maintenance.md) permits a verified host operator to authorize continued eligible cleanup on the same unfinished recovery, with the same twelve-attempt/one-hour limits for each new run. There is no lifetime cap on explicit authorizations.

Keep each authorization and budget separate, retaining earlier history and confirmed progress. Deduplicate operator requests and prevent parallel runs for an already-active budget. Neither approval nor retry releases the block or supplies missing completion evidence. [Host maintenance](host-maintenance.md#recovery-cleanup-continuation) owns authority, and [the continuation workflow](recovery-completion.md#operator-cleanup-continuation) owns behavior. Exact transport, persistence and execution remain unfinished.

## Accepted failure handling

On 2026-10-25, the developer selected retries for recoverable provider failures and uncertain bulk-cleanup outcomes within the run budget. A known permanent rejection ends the current run early, preserves progress and the recovery block, and requires operator attention. After fixing the cause, a verified host operator may authorize another bounded run without waiting for the ended run's deadline.

[The owning failure policy](recovery-completion.md#hydra-cleanup-failure-handling) separates cleanup observations from retryability. Exact provider-error mappings and the safe evidence needed to apply them remain unfinished. The current confirmed/failed/uncertain result is not that complete classification contract. No blanket retry of programming errors is selected. This is an implementation-contract refinement of the existing retry and continuation decisions, not a new ADR or runtime behavior.

## Decision trigger and stopping boundary

Before wiring production recovery admission/completion callbacks, cleanup orchestration, issuance coordination or block release.

The unresolved correlation, reconciliation and completion details gate dependent production wiring. The hook choice, retry limits, operator-continuation and failure-handling policies are settled. Existing local checklist tests and provider qualification experiments may proceed without inventing successful completion.

## Architectural impact and dependencies

Access recovery coordinator, private callback validation, Kratos settings/recovery integration, Hydra cleanup and consent/refresh coordination, shared jobs and recovery sequence diagrams. No new public recovery API is selected here.

Load neighboring decisions only under these conditions:

- [Resolved PD-ACCESS-04](decision-recovery-first-admission.md) and its [accepted identity-coordination workflow](identity-admission-coordination.md). When the identity has no local account or first admission overlaps cleanup. The design is settled. Recovery admission/completion and initialization use the shared coordinator, while complete first admission remains unfinished.
- [PD-ACCESS-02: Keep durable work and credential lifetime explicit](decision-admitted-work-authority.md). When recovery must stop already-admitted product work.

## Open questions and required evidence

- How does production validate the selected post-persistence callback's original recovery/settings association and identity, including restarted settings flows?
- When can the aggregate Hydra outcome be called confirmed despite overlapping issuance?
- How are lost acknowledgments, restarts and overlapping flows reconciled?
- What exact backoff intervals, provider-error mappings and safe failure observations implement the selected retry policy?
- What durable authorization/budget/progress representation preserves ended-run reasons and independent cleanup uncertainty?
- What protected operator command/input contract implements the selected continuation policy with deduplication and active-run coordination?

## Sources and finalization

- [Recovery and provider observations](recovery.md#identity-recovery-cleanup).
- [Private callback contract](private-recovery-handoff.md#recovery-callbacks).
- [Private recovery handoff](private-recovery-handoff.md#recovery-wire).
- [Independent release](../../../../docs/adr/ADR-0069-release-completed-recovery-obligations-independently.md).
- [Bulk Hydra cleanup](../../../../docs/adr/ADR-0070-use-bulk-hydra-revocation-for-identity-recovery.md).
- [Accepted native-hook approach](../../../../docs/adr/ADR-0081-use-native-kratos-hooks-for-recovery-evidence.md) and [documented provider support](recovery-provider-cleanup.md#documented-native-hook-support).
- [Accepted Hydra retry limits](../../../../docs/adr/ADR-0083-bound-hydra-recovery-cleanup-retries.md) and [owning retry policy](recovery-completion.md#hydra-cleanup-retry-budget).
- [Accepted host-authorized continuation](../../../../docs/adr/ADR-0084-authorize-additional-recovery-cleanup-runs-through-host-maintenance.md) and [owning continuation policy](recovery-completion.md#operator-cleanup-continuation).
- [Accepted failure handling](recovery-completion.md#hydra-cleanup-failure-handling), with implementation notes in ADR-0083 and ADR-0084.

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
