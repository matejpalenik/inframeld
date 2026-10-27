# ADR-0083: Bound Hydra recovery-cleanup retries

**Status:** Accepted policy. [ADR-0084](ADR-0084-authorize-additional-recovery-cleanup-runs-through-host-maintenance.md) defines separately authorized operator continuation. The dedicated worker implements bounded retry orchestration, and the protected maintenance command authorizes additional runs.

**Date:** 2026-10-25

## Context and Problem Statement

Alice has saved her replacement password and Kratos session cleanup is confirmed, but Hydra is temporarily unavailable. Inframeld must preserve her recovery block and confirmed progress while giving unfinished Hydra cleanup a bounded opportunity to finish automatically.

The shared job guide currently allows at most three application attempts. That limit can require operator attention after a few quick failures. The developer selected a one-hour automatic retry window and then explicitly approved twelve cleanup attempts as a narrow exception under [PD-ACCESS-03](../../.agents/skills/inframeld-access-models/references/decision-recovery-production-completion.md). These are Inframeld policy choices, not provider-prescribed retry values.

## Considered Options

- A fifteen-minute window or a one-hour window before requiring operator attention. One hour was selected to give temporary provider outages more time to recover automatically.
- Keep the shared three-attempt limit or allow twelve attempts for Hydra recovery cleanup. Twelve was selected for this operation. Other jobs retain their existing limit.

## Decision Outcome

Allow at most twelve cleanup attempts in the original recovery operation's initial automatic run, including the initial attempt, within a one-hour maximum after trusted Kratos completion makes Hydra cleanup eligible. Both limits apply. Stop new automatic attempts when either is exhausted.

Preserve the original deadline and attempt count across worker restarts and duplicate callbacks. Retry only unfinished cleanup with progressively longer waits. Keep confirmed progress durable so later attempts do not repeat a confirmed step. Missing password-replacement or native session-cleanup evidence does not make Hydra cleanup eligible.

The exception covers the original operation's CLI-grant and remembered-login cleanup together. It does not give each provider method or replacement worker a fresh budget. Individual SDK calls retain their bounded deadlines and disabled automatic retries. No recovery block is released because a timer or attempt counter expires.

The [Access-owned retry policy](../../.agents/skills/inframeld-access-models/references/recovery-completion.md#hydra-cleanup-retry-budget) specifies progress and exhaustion behavior. Shared durable ownership and uncertainty rules from [ADR-0026](ADR-0026-persist-background-work-through-controlled-durable-attempts.md) remain in force.

[ADR-0084](ADR-0084-authorize-additional-recovery-cleanup-runs-through-host-maintenance.md) resolves the operator follow-up left open by this decision. A fresh explicit host authorization can grant another bounded run on the same unfinished recovery. It records a separate budget while preserving the initial count, deadline and all progress. Automatic restarts and duplicate events still grant no new budget, and the original retry-limit rationale is unchanged.

## Consequences

- Temporary Hydra outages have more automatic recovery opportunities, while dispatch remains bounded by both elapsed time and attempts.
- Exhaustion preserves the original obligation, confirmed progress and uncertain outcomes. Alice remains blocked and the unresolved operation requires operator attention.
- Already-dispatched calls may still finish after timeout or budget exhaustion. An unfinished bulk retry can affect newer Alice credentials under ADR-0070. Completed duplicate events still initiate no new cleanup.
- Other job types keep their three-attempt limit. This policy introduces no nested SDK retry loop, queue or workflow engine.
- [ADR-0085](ADR-0085-bind-password-settings-evidence-to-original-recoveries.md) resolves PD-ACCESS-03. [The completion reference](../../.agents/skills/inframeld-access-models/references/recovery-completion.md#hydra-cleanup-retry-budget) owns exact persisted backoff, Retry-After handling and provider-error mappings. [Logical records](../../.agents/skills/inframeld-access-models/references/credential-and-recovery-records.md#recovery-delivery-records) and [protected host input](../../.agents/skills/inframeld-access-models/references/host-maintenance.md#recovery-cleanup-continuation) describe the implemented persistence and command. Runtime implementation was unfinished when this policy was accepted. The later dedicated worker and maintenance command implement it within the owning references' limits. Operator continuation policy remains ADR-0084. This policy decision itself introduced no code, configuration, schema or runtime test evidence.

## Implementation notes

On 2026-10-25, the developer selected [retries for recoverable failures and uncertain bulk outcomes](../../.agents/skills/inframeld-access-models/references/recovery-completion.md#hydra-cleanup-failure-handling), with early termination for a known permanent rejection. The attempt/time limits are upper bounds, not a requirement to repeat a known-invalid request. Preserve cleanup observations, progress and the block when ending a run. The policy refinement itself changed no adapter and introduced no blanket programming-error retries. The later adapter implements the separate outcome/disposition result, and the dedicated worker implements durable orchestration under the owning completion reference. The [implementation and behavioral tests](../../.agents/skills/inframeld-access-models/references/recovery-completion.md#implemented-execution-and-proof-backed-completion) are separate from the original decision.

## Links

- [Shared job policy](../../.agents/skills/inframeld-application-contracts/references/jobs-and-recovery.md#preserve-progress-and-distinguish-failure-from-uncertainty) and [logical recovery records](../../.agents/skills/inframeld-access-models/references/credential-and-recovery-records.md#identity-cleanup-records).
- [ADR-0070: Bulk Hydra cleanup](ADR-0070-use-bulk-hydra-revocation-for-identity-recovery.md), [ADR-0081: Native hook evidence](ADR-0081-use-native-kratos-hooks-for-recovery-evidence.md) and [resolved PD-ACCESS-03 contract](../../.agents/skills/inframeld-access-models/references/decision-recovery-production-completion.md).
