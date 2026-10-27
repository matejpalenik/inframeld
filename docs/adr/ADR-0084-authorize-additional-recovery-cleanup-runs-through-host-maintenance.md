# ADR-0084: Authorize additional recovery-cleanup runs through host maintenance

**Status:** Accepted and implemented for recovery-cleanup continuation. Other maintenance modes remain separate.

**Date:** 2026-10-25

## Context and Problem Statement

Alice's automatic Hydra cleanup exhausts its budget. The server operator fixes the underlying problem and needs a supported way to continue unfinished work. A limit on unattended retries must not become a lifetime limit on explicit operator intervention.

[ADR-0083](ADR-0083-bound-hydra-recovery-cleanup-retries.md) selected twelve attempts within one hour and left operator follow-up unresolved. The developer approved another bounded run on the same original recovery, preserving its history and confirmed progress. This resolves that part of [PD-ACCESS-03](../../.agents/skills/inframeld-access-models/references/decision-recovery-production-completion.md).

## Considered Options

- Allow a verified host operator to authorize another bounded run. The operator gives one explicit approval, then safe unfinished cleanup can retry automatically within that run's limits.
- Allow one additional attempt per explicit operator approval. This gives finer manual control but requires the operator to supervise each retry after another failure.

## Decision Outcome

Choose another bounded run through the protected host-maintenance boundary. Each additional run permits up to twelve attempts, including its first attempt, within one hour of its recorded authorization. Each further run requires fresh explicit operator authorization. There is no lifetime cap on those authorizations.

Keep the original recovery operation and its installation/provider/identity binding. Record each new authorization and budget separately. Preserve every earlier count, deadline, outcome and durably confirmed step. Restart, callback delivery or repetition of the same operator request cannot grant another budget.

Only unfinished recovery cleanup may continue. A distinct authorization must not start a parallel run while a budget is active. A completed recovery cannot restart, and confirmed steps are not repeated. Missing trusted Kratos completion evidence still prevents Hydra cleanup from becoming eligible.

Host authority authorizes continued cleanup, not product access. A run does not release the block, restore an account, recreate permissions or advance the credential version. Existing trusted-evidence and local eligibility checks still govern completion.

The [Access-owned continuation workflow](../../.agents/skills/inframeld-access-models/references/recovery-completion.md#operator-cleanup-continuation) defines the rules. [Host maintenance](../../.agents/skills/inframeld-access-models/references/host-maintenance.md#recovery-cleanup-continuation) owns the authority boundary. [ADR-0085](ADR-0085-bind-password-settings-evidence-to-original-recoveries.md) resolves the protected input and logical persistence contract. The implemented recovery mode is described below.

## Consequences

- Operators can repair dependencies and authorize continued cleanup without supervising every safe retry.
- The initial and later runs remain bounded. No worker or callback can renew a budget automatically, and previous budgets remain part of the operation's history.
- Concurrent and repeated authorization requests need durable deduplication and active-run checks. These requirements select no new table, job state or public endpoint.
- Already-dispatched provider calls may finish late. A new run does not prove they stopped or change the accepted effects of bulk cleanup on newer Alice credentials.
- Ordinary product credentials do not supply host authority. Other jobs retain their existing attempt limits. At policy acceptance, production completion was unwired. The dedicated recovery worker now applies proof-backed local completion.
- This documentation decision introduces no application code, configuration, migrations or new runtime evidence.

## Implementation notes

The accepted [failure policy](../../.agents/skills/inframeld-access-models/references/recovery-completion.md#hydra-cleanup-failure-handling) may end a run early for a known permanent rejection. After fixing the cause, a verified host operator may authorize another bounded run immediately. They need not wait for the ended run's deadline. Preserve its stop reason, consumed attempts, original deadline, confirmed progress and independent provider uncertainty.

An ended run no longer supplies an active budget. A fresh authorization creates a separate run rather than reviving unused attempts. Distinct requests still cannot start parallel active runs. This clarification neither releases the recovery block nor supplies missing Kratos evidence. [ADR-0085](ADR-0085-bind-password-settings-evidence-to-original-recoveries.md) finalizes the owning failure mapping and record contract. The host command takes a unique request ID and original recovery ID, with no reviewed-run ID, recipient token or ordinary product-session requirement. Current-state checks and active-run exclusion remain mandatory. The recovery mode now uses one immutable maintenance receipt as both replay record and operator audit history. Migration 0008 makes request-key uniqueness immediate and defers only the optional new-run foreign key, so the complete receipt is inserted before run changes in one transaction. No organization-scoped audit event or synthetic operator principal is introduced. The command leaves provider dispatch and release to the existing worker.

## Links

- [ADR-0083: Initial retry limits](ADR-0083-bound-hydra-recovery-cleanup-retries.md), [ADR-0070: Bulk Hydra scope](ADR-0070-use-bulk-hydra-revocation-for-identity-recovery.md) and [resolved PD-ACCESS-03 contract](../../.agents/skills/inframeld-access-models/references/decision-recovery-production-completion.md).
- [Logical recovery records](../../.agents/skills/inframeld-access-models/references/credential-and-recovery-records.md#identity-cleanup-records) and [shared resume behavior](../../.agents/skills/inframeld-application-contracts/references/jobs-and-recovery.md#resume-the-same-job-only-when-the-remaining-work-is-safe).
