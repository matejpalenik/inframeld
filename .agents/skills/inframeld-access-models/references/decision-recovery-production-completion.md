# PD-ACCESS-03: Prove recovery cleanup before releasing product access

**Status:** RESOLVED for the production delivery contract on 2026-10-25 under [ADR-0085](../../../../docs/adr/ADR-0085-bind-password-settings-evidence-to-original-recoveries.md). Runtime implementation and qualification remain unfinished in #243–#245. This is not evidence that production recovery can already release access.

**Owner:** `inframeld-access-models`

## Problem and example

Alice proves a recovery code, restarts password settings and loses a callback response. Hydra can also finish an older approval or refresh during cleanup. Inframeld must preserve the original obligation, obtain trustworthy password/session evidence and continue only safe unfinished work. A generic authenticated webhook proves its sender, not the whole cleanup.

## Accepted contracts

| Question | Resolution and owning reference |
| --- | --- |
| Which native events count? | Recovery-code verification admits the original obligation. Native settings-flow creation binds its session. Only the password hook after persistence and native session revocation supplies Kratos cleanup proof. [Private handoff](private-recovery-handoff.md#native-hook-evidence). |
| How are restarted settings flows matched? | Version 2 evidence plus a durable exact identity/session association. An ordinary settings query cannot establish it. [Evidence contract](private-recovery-handoff.md#recovery-wire). |
| What if completion evidence is lost permanently? | Save again through the trusted association, or perform a new verified recovery. The new admission captures explicit links to older unfinished operations. Its complete combined proof can satisfy those original checklists separately. [Reconciliation](private-recovery-handoff.md#recover-original-evidence). |
| What permits release despite late Hydra issuance? | Trusted Kratos proof, both durably acknowledged scoped Hydra requests, intact identity/version binding and current local eligibility. Old-version tokens stay invalid at Inframeld after release. [Completion proof](recovery-completion.md#completion-proof). |
| What survives restart? | Receipts, associations, proof links, original job/progress, separate runs, consumed attempts and host authorization outcomes. [Logical records](credential-and-recovery-records.md#recovery-delivery-records). |
| How are attempts bounded? | Twelve per run, one hour, persisted positive capped exponential jitter and provider `Retry-After` lower bounds. Explicit response mappings separate uncertainty from retryability. [Retry budget](recovery-completion.md#hydra-cleanup-retry-budget) and [failure mapping](recovery-completion.md#hydra-cleanup-failure-handling). |
| What can the host operator authorize? | A new bounded run for the original eligible recovery, using a unique request ID. No reviewed-run ID or Alice token. Current active-run checks and replay preserve history. [Host contract](host-maintenance.md#recovery-cleanup-continuation). |

## Alternatives and rationale

Native hooks plus durable reconciliation remain selected over treating a generic callback as complete proof or introducing another private password-verification service. The fixed five-field envelope is superseded because it cannot express native settings/session association. Requiring the original lost receipt forever is replaced by explicit newer-to-older proof links, without allowing an older operation to clear a newer block.

The earlier retry decisions remain: [ADR-0083](../../../../docs/adr/ADR-0083-bound-hydra-recovery-cleanup-retries.md) permits twelve attempts within one hour, while other jobs keep three. [ADR-0084](../../../../docs/adr/ADR-0084-authorize-additional-recovery-cleanup-runs-through-host-maintenance.md) permits unlimited explicit additional host-authorized runs, not unlimited unattended retries. Known permanent rejections end a run early. The operator can authorize another after fixing the cause without waiting for its former deadline.

Requiring a reviewed ended-run ID was considered and not selected. The simpler instruction authorizes eligible unfinished work against current state. A unique request ID prevents repeated accepted delivery from creating another budget, and current-state coordination prevents parallel active runs. No maintenance authorization supplies missing provider proof or product access.

<a id="non-binding-recommendation"></a> <a id="decision-trigger-and-stopping-boundary"></a>

## Delivery boundary and neighboring decisions

The design questions above no longer gate #243–#245. Each implementation still needs separate named-file write approval, its behavioral tests and its applicable qualification. Never report a specification, local checklist test or provider fixture as production completion. If pinned-provider behavior contradicts a required association or guarantee, report the conflict rather than silently weakening it.

[Resolved identity coordination](identity-admission-coordination.md) applies to short database steps before organization/project locks, including identities without local accounts. Its three recovery/initialization participants are implemented. Complete first admission remains separate. Provider waits hold no SQL transaction.

[PD-ACCESS-02](decision-admitted-work-authority.md) applies only if work must decide whether already-admitted product jobs survive credential changes. [PD-CONTRACTS-05](../../inframeld-application-contracts/references/decision-queue-saturation-and-cleanup.md) applies when selecting scheduling/saturation behavior or claiming progress under load. This resolution does not choose those unrelated policies or a new queue.

<a id="open-questions-and-required-evidence"></a>

## Required behavioral evidence

The design is settled. These are runtime acceptance scenarios, not new pending policy choices:

| Consumer | Scenario | Required result |
| --- | --- | --- |
| #243 | Anonymous recovery email request | No admission, block or version change. |
| #243 | Valid code, failed admission commit | No successful receipt or unblocked continuation. |
| #243 | Duplicate admission or lost acknowledgment | Same original operation and one version advancement. |
| #243 | Wrong identity, conflicting session/source, unknown fields or invalid service key | Safe rejection without recovery effects. |
| #243 | Ordinary settings with a recovery query parameter, or conflicting query/body IDs | Cannot establish a recovery association or completion proof. |
| #243 | Native initial flow and restarted flow in its bound session | Preserve the original operation despite different settings-flow IDs. |
| #243 | Password persisted but callback lost | Keep the block. Replay a saved receipt or obtain fresh trusted proof without claiming rollback. |
| #243/#244 | New verified recovery after old evidence/session expires | Capture older operation links once. Only complete combined proof satisfies them. Never cover a later recovery or Bob. |
| #244 | Only one Hydra step confirmed | Retain its checkpoint and keep the block. |
| #244 | Crash after dispatch or before checkpoint | Preserve attempt consumption and uncertainty. Retry only safe unfinished work. |
| #244 | Replacement worker or stale ownership token | Retain budget/timing. Reject stale progress and skip confirmed steps. |
| #244 | Each specified provider status, malformed response, timeout and cancellation | Match the safe outcome/disposition contract with no SDK retry multiplication. |
| #244 | Restart during backoff, `Retry-After`, deadline or attempt exhaustion | Preserve the chosen time and limits. No fresh dispatch beyond budget and no timer-based release. |
| #244 | Newer combined proof satisfies linked old checklists | Preserve original records and history, end old dispatch, and apply eligibility separately to each. |
| #244 | Late approval/refresh, then release | Old-version credentials and their descendants remain rejected by Inframeld. Fresh eligible credentials work. |
| #244 | No local account, suspended account, overlapping recoveries | No account creation, no automatic suspension override and no older-to-newer block release. |
| #244 | Provider cleanup confirmed, local completion interrupted | Retry local completion only, without more provider calls. |
| #245 | Lost operator acknowledgment or changed meaning under the same request ID | Replay the original authorization or conflict, never a fresh budget. |
| #245 | Two different requests race | At most one active run for the original recovery. No reviewed-run ID is required. |
| #245 | Missing Kratos proof, completed recovery or no remaining provider work | No new run, manufactured proof, credential-version change or block release. |

Existing provider tests remain supporting evidence with their recorded limits. The complete production path still needs native hook delivery, database failure/restart injection, worker execution and the protected host boundary. A failing required scenario remains a delivery gap.

## Sources and finalization

- [ADR-0081: Native hooks](../../../../docs/adr/ADR-0081-use-native-kratos-hooks-for-recovery-evidence.md), [ADR-0085: Association and reconciliation](../../../../docs/adr/ADR-0085-bind-password-settings-evidence-to-original-recoveries.md) and [documented provider support](recovery-provider-cleanup.md#documented-native-hook-support).
- [Independent release](../../../../docs/adr/ADR-0069-release-completed-recovery-obligations-independently.md), [bulk cleanup](../../../../docs/adr/ADR-0070-use-bulk-hydra-revocation-for-identity-recovery.md) and [credential versions](human-cli-credential-lifecycle.md#human-credential-versions).
- [Recovery overview](recovery.md), [private handoff](private-recovery-handoff.md), [completion](recovery-completion.md), [records](credential-and-recovery-records.md#recovery-delivery-records) and [maintenance](host-maintenance.md#recovery-cleanup-continuation).

The resolution follows [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). #242 tracks specification delivery and remains open until merge. Runtime implementation, qualification and any later architectural conflict must be recorded separately.
