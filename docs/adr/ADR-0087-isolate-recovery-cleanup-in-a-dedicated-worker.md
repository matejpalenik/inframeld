# ADR-0087: Isolate recovery cleanup in a dedicated worker

**Status:** Accepted

**Date:** 2026-10-26

## Context and Problem Statement

Alice's recovery must not wait for Bob's document-processing job to relinquish the only worker slot. Queue priority would still leave the current long-running job occupying that slot.

## Considered Options

- One shared worker with oldest-due-job-first scheduling.
- A shared worker with recovery priority or reserved execution slots.
- One dedicated recovery process alongside the future application worker.

## Decision Outcome

Use a dedicated recovery worker from the same backend image, with one active attempt and PostgreSQL-backed ownership and checkpoints. It handles recovery cleanup and local proof reconciliation only. Authentication and consent remain in their existing request processes.

This refines the earlier single-worker convention. It adds no queue broker, generic scheduler or domain service framework. Take due provider jobs in oldest-first order with an operation-ID tie-break, with bounded pages of local proof checks between attempts. Keep all provider waits outside database transactions.

**Example.** Bob's parser can occupy the application worker while Alice's separate recovery worker revokes her CLI credentials. A replacement recovery worker preserves the original budget and skips saved confirmations.

## Consequences

- Application jobs do not occupy recovery's execution slot. Shared CPU, database and provider resources can still delay it. This supplies no latency or saturation guarantee.
- Support one recovery process with one active attempt. Ownership tokens still reject stale results during replacement or accidental overlap.
- Provider cleanup, trusted evidence and local eligibility remain distinct. Worker isolation grants no permission to release a block.
- Broader queue admission, fairness and resource-envelope decisions remain pending. This decision selects only recovery isolation and its simple claim order.

## Links

- [Durable attempts](ADR-0026-persist-background-work-through-controlled-durable-attempts.md)
- [Recovery completion](../../.agents/skills/inframeld-access-models/references/recovery-completion.md)
- [Runtime topology](../../.agents/skills/inframeld-architecture/references/runtime-deployment-and-storage.md)
- [Saturation policy, subsequently accepted under ADR-0102](../../.agents/skills/inframeld-application-contracts/references/decision-queue-saturation-and-cleanup.md)

## Later resolution

[ADR-0102](ADR-0102-use-bounded-fifo-with-separate-recovery-execution.md) records the developer-approved 2026-10-29 policy for the temporal or queue question left open here. The earlier component/recovery-isolation choice remains accepted.
