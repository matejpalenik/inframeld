# PD-CONTRACTS-05: Qualify cleanup and recovery under a full bounded queue

**Status:** ACCEPTED on 2026-10-29 in [ADR-0102](../../../../docs/adr/ADR-0102-use-bounded-fifo-with-separate-recovery-execution.md). Implementation and qualification remain pending.

**Owner:** `inframeld-application-contracts`

**Issue kind:** Operating-policy recommendation and qualification.

The developer explicitly approved all three permissions-and-jobs proposals on 2026-10-29 and requested repository and GitHub documentation. Acceptance selects the policy, not implemented behavior or passing qualification.

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

Project A starts a large evaluation and the finite queue fills with other work. Bob needs recovery cleanup, and old artifacts must be removed before disk headroom runs out. Access blocks can remain safe even while their cleanup waits, but users and operators need an honest outcome.

Queue/concurrency limits, checkpoints, saturation rejection and safe storage admission are already required. The review did not find a promised fairness, priority or yielding policy. This resolution selects simple claim behavior. Its cleanup and recovery consequences still require qualification.

## Accepted context and evidence

Preserve PostgreSQL-backed durable work, bounded attempts/backoff/deadlines and current checks. [ADR-0087](../../../../docs/adr/ADR-0087-isolate-recovery-cleanup-in-a-dedicated-worker.md) selects one dedicated recovery worker alongside the future application worker, with oldest-due-original ordering inside recovery. That earlier decision did not settle product queue saturation. This resolution now selects that policy, while numerical resource guarantees remain separate. Deletion/recovery use existing durable mechanics. Tombstones and recovery blocks protect access before physical/provider work finishes. Workload-priority budget hierarchies remain deferred.

A finite queue limits total admitted work, not waiting time between projects. Monitoring the oldest job observes delay but does not resolve it. A new scheduler or reserved capacity is not required merely because no latency evidence exists.

## Alternatives and trade-offs

These alternatives preserve the pre-approval discussion. The approved resolution below selects the current contract.

1. **Use bounded FIFO with explicit saturation/operator behavior.** Claim in a documented simple order and reject/delay within measured limits. This is maintainable, but cleanup/recovery may wait behind bulk work.
2. **Add a narrowly justified cleanup/claim rule after measurement.** Use bounded checkpoint yielding or a specific admissible cleanup rule if the simple profile fails its requirements. This can improve recovery, but adds scheduling state and needs explicit approval without becoming a priority framework.

## Approved resolution

Keep PostgreSQL-backed jobs, one active application-worker attempt, and the separate one-attempt recovery worker already selected by ADR-0087. Do not add a broker, general priority framework or another worker pool in this decision.

For ordinary application jobs, choose the oldest durably admitted job among eligible due jobs, with a stable job-ID tie-break. Backoff, stale ownership, unsupported payloads and terminal states do not become runnable merely because they are old. A running job keeps its slot until completion, failure, cancellation or its bounded deadline. Checkpoints observe authority/cancellation and preserve progress. They do not imply preemption or round-robin yielding.

Count queued and running admitted jobs against a finite configured capacity. Check and reserve that capacity atomically with admission, so concurrent requests cannot both take the last slot. Reject new ordinary work before its business effects if capacity is unavailable. Never report admission and then drop the job.

If a new deletion needs a cleanup job and cannot admit it atomically, reject that new deletion before its business effects. Do not commit an untracked cleanup obligation. Already accepted deletion/cleanup obligations remain durable and keep their place. Revocation, suspension and cancellation checks do not require a new ordinary queue slot. Identity recovery retains its separate existing execution and admission mechanics and never becomes ordinary product work.

Product cleanup can wait behind a bounded ordinary application job. New arrivals cannot continually jump ahead of an already eligible older cleanup job. Account and erasure blocks continue denying access while physical cleanup is incomplete. The separate recovery process avoids waiting for the application execution slot, but shares hardware and dependencies and has no guaranteed response time.

After restart, preserve original ordering, ownership checks, budgets and known effects. Retry only established safe work under existing bounds. Expose queue depth, age of oldest eligible work, worker health and cleanup delay through the existing operational surfaces. Low storage stops unsafe admissions and is not permission to drop cleanup records or weaken security restrictions.

Numerical capacities, operation deadlines and supported delay objectives belong to the later PD-ARCHITECTURE-01 operating-profile batch. Approving this proposal selects the scheduling/saturation policy, not unmeasured numerical guarantees.

## Decision trigger and stopping boundary

Apply this accepted contract when the affected implementation reaches its original trigger. Ordinary representation and method-name choices remain implementation work. A change to the selected policy requires a new explicit decision. Missing qualification limits claims, not authorized evidence gathering.

## Architectural impact and dependencies

Shared job claims/checkpoints/admission, identity cleanup, source/project erasure and low-disk handling. Update queue/cleanup sequences if the actual chosen behavior changes.

Load neighboring decisions only under these conditions:

- [PD-ARCHITECTURE-01 (accepted): Select a measured supported workload and resource envelope](../../inframeld-architecture/references/decision-supported-operating-envelope.md). For measured limits and any supported latency objective.
- [PD-ACCESS-02: Keep durable work and credential lifetime explicit](../../inframeld-access-models/references/decision-admitted-work-authority.md). When checkpoint timing implements authority restrictions.

## Implementation and required evidence

The following are required behavioral cases, not executed test results.

- Concurrent requests for the final queue slot admit at most one new job.
- Restart preserves original jobs, safe ordering and retry budgets.
- Recovery executes independently of a busy application-worker slot.
- Queue saturation does not block cancellation/revocation or lose accepted cleanup.
- Mixed load, sustained saturation and low disk retain safe failures and honest incomplete-cleanup status. Passing numbers require actual measurements.

## Sources and finalization

- [Bounded worker mechanics](jobs-and-recovery.md#admit-work-and-claim-an-attempt).
- [Deletion obligations](../../inframeld-knowledge/references/deletion-and-retention.md).
- [Operational bounds](../../inframeld-architecture/references/runtime-deployment-and-storage.md).

The approved resolution is recorded in [ADR-0102](../../../../docs/adr/ADR-0102-use-bounded-fifo-with-separate-recovery-execution.md). Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later policy change. This documentation approval does not authorize application implementation or claim runtime qualification.
