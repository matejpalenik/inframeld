# ADR-0102: Use bounded FIFO with separate recovery execution

**Status:** Accepted

**Date:** 2026-10-29. The developer explicitly approved all three permissions-and-jobs proposals on 2026-10-29 and requested repository and GitHub documentation. Acceptance selects the policy, not implemented behavior or passing qualification.

## Context and Problem Statement

A bounded single-host queue needs a documented claim order and honest behavior when full. Recovery already has its own worker under ADR-0087.

## Considered Options

- Use bounded FIFO and retain dedicated recovery execution. Selected.
- Add checkpoint yielding or cleanup priority, with additional scheduling and attempt-lifetime complexity.

## Decision Outcome

Use oldest-admitted eligible due application jobs with a stable job-ID tie-break, one application attempt and the existing separate recovery attempt. Count queued/running jobs against atomically reserved finite capacity. Reject new work before effects when admission cannot succeed. Existing cleanup stays durable. Revocation, suspension and cancellation require no new ordinary queue slot.

The [approved PD-CONTRACTS-05 contract](../../.agents/skills/inframeld-application-contracts/references/decision-queue-saturation-and-cleanup.md#approved-resolution) owns the complete behavior and examples.

## Consequences

Long product jobs can delay shorter jobs and product cleanup. Checkpoints do not imply preemption. Numerical caps, deadlines and delay objectives remain with PD-ARCHITECTURE-01. This refines saturation policy without replacing recovery isolation or adding a scheduler/broker.

Implementation, tests and production qualification remain separate delivery work. No application code or public schema is delivered by this documentation decision.

## Links

- [Stable decision reference](../../.agents/skills/inframeld-application-contracts/references/decision-queue-saturation-and-cleanup.md)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
