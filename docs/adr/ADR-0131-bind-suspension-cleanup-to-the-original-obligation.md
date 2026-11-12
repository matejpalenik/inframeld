# ADR-0131: Bind suspension cleanup to the original obligation

**Status:** Accepted. Partially supersedes [ADR-0087](ADR-0087-isolate-recovery-cleanup-in-a-dedicated-worker.md) for the recovery worker's routine-only scope. The shared recovery-worker implementation and selected local PostgreSQL and pinned Ory qualification are complete. [Human qualification #318](https://github.com/matejpalenik/inframeld/issues/318) remains separate from automated evidence.

**Date:** 2026-11-12

## Context and Problem Statement

Bob suspends Alice when the ordinary application queue is full and Ory is unavailable. Access must commit her local block and durable cleanup obligation before returning `202`. The operator needs to inspect that exact original and authorize safe continuation after an ambiguous provider response. [ADR-0102](ADR-0102-use-bounded-fifo-with-separate-recovery-execution.md) keeps suspension independent of ordinary queue capacity. [ADR-0127](ADR-0127-fence-human-authentication-evidence-at-restoration.md) requires confirmed original cleanup before deliberate restoration.

## Considered Options

The earlier proposal put cleanup on the ordinary worker, requiring a capacity handoff and private provider administration access there. A new isolated worker or provider proxy would add a deployment component. The developer chose the existing recovery worker with one shared bounded attempt and one operator-authorized repeat within the original limits.

## Decision Outcome

Commit the block, audit, Access revision, original result, exact cleanup obligation and one fixed typed queued child together. Exclude suspension work from ordinary capacity, running slots, pressure, candidate selection and generic effect and lifecycle paths. Preserve ordinary FIFO.

The recovery process owns routine recovery and suspension cleanup, with one live fenced local attempt across both. Start with routine recovery and alternate the first opportunity, trying the other family if the first cannot progress. Preserve each family's stable order, routine reconciliation and shutdown. Both claim paths serialize through the same short installation turn and check fresh live occupancy before claiming. [Recovery completion](../../.agents/skills/inframeld-access-models/references/recovery-completion.md#suspension-cleanup) owns the exact ordering and guard.

Give that process private Kratos administration access alongside its existing Hydra access through pinned process-owned clients. The ordinary worker retains its existing configuration. Only the recovery worker dispatches the three fixed suspension steps under the exact original binding and live fence. Store the dispatch marker before provider I/O and independently confirm each step under the same checked scope. Keep provider waits outside SQL and preserve the original limits.

Use the existing [protected host command](../../.agents/skills/inframeld-access-models/references/host-maintenance.md#suspension-cleanup-maintenance) to inspect safe current state or explicitly continue the exact original. Continue uses the shared operator request namespace and an immutable typed receipt. It can authorize one repeat of an exact unresolved step within the original schedule, attempts and deadlines. Consume the authorization once with the next live dispatch marker. Earlier ambiguous dispatch remains uncertain. The command performs local work only.

## Consequences

- Suspension and its cleanup slot are independent of ordinary queue saturation. Routine recovery and suspension cleanup may wait behind each other, and shared resources can delay either.
- Support one recovery worker. Retire an older binary before first starting the guard-enabled replacement. The guard bounds live local claims, while an earlier remote call can finish after ownership expires.
- Private provider reach belongs to this worker deployment. The three adapter methods constrain the application workflow. They do not limit the provider authority available to a compromised process with private administration reach.
- Preserve routine recovery's separate proof, run budgets and host mode. Suspension uses its original 24-hour queue deadline, first-claim work deadline, bounded lease/backoff and three-attempt maximum.
- Restore only after all three original confirmations and the existing current authority, same-identity review and independent-block checks. ADR-0127's once-only version advance and accepted late-session limit remain in force.
- Qualification must cover full ordinary capacity, shared claim ordering and ownership, original deadlines, one repeat and its receipt, unknown effects, real pinned Ory behavior, and unchanged routine and ordinary work. Registered HTTP, generated-client and human evidence remain separate.

## Links

- [Recovery worker isolation](ADR-0087-isolate-recovery-cleanup-in-a-dedicated-worker.md), [ordinary queue policy](ADR-0102-use-bounded-fifo-with-separate-recovery-execution.md) and [restoration cutover](ADR-0127-fence-human-authentication-evidence-at-restoration.md).
- [Suspension records](../../.agents/skills/inframeld-access-models/references/credential-and-recovery-records.md#suspension-cleanup-records) and [runtime boundary](../../.agents/skills/inframeld-architecture/references/runtime-deployment-and-storage.md#trace-public-and-private-access).
- [Delivery #188](https://github.com/matejpalenik/inframeld/issues/188) and [human qualification #318](https://github.com/matejpalenik/inframeld/issues/318).
