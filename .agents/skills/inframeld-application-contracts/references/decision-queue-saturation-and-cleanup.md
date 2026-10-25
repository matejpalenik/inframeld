# PD-CONTRACTS-05: Qualify cleanup and recovery under a full bounded queue

**Status:** PENDING

**Owner:** `inframeld-application-contracts`

**Issue kind:** Operating-policy recommendation and qualification.

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

Project A starts a large evaluation and the finite queue fills with other work. Bob needs recovery cleanup, and old artifacts must be removed before disk headroom runs out. Access blocks can remain safe even while their cleanup waits, but users and operators need an honest outcome.

Queue/concurrency limits, checkpoints, saturation rejection and safe storage admission are already required. The review did not find a promised fairness, priority or yielding policy. The remaining recommendation is to select/document simple claim behavior and test its consequences for cleanup and recovery.

## Accepted context and evidence

Preserve one supported worker/queue, bounded attempts/backoff/deadlines and current checks. Deletion/recovery use existing durable mechanics. Tombstones and recovery blocks protect access before physical/provider work finishes. Workload-priority budget hierarchies remain deferred.

A finite queue limits total admitted work, not waiting time between projects. Monitoring the oldest job observes delay but does not resolve it. A new scheduler or reserved capacity is not required merely because no latency evidence exists.

## Alternatives and trade-offs

1. **Use bounded FIFO with explicit saturation/operator behavior.** Claim in a documented simple order and reject/delay within measured limits. This is maintainable, but cleanup/recovery may wait behind bulk work.
2. **Add a narrowly justified cleanup/claim rule after measurement.** Use bounded checkpoint yielding or a specific admissible cleanup rule if the simple profile fails its requirements. This can improve recovery, but adds scheduling state and needs explicit approval without becoming a priority framework.

## Non-binding recommendation

**Proposal only.** Start with bounded FIFO as a viable proposal and qualify mixed-load behavior. Add only the smallest change justified by a failed selected objective. Do not retroactively declare fairness or reserved production capacity to be an existing requirement.

## Decision trigger and stopping boundary

When selecting worker claim/scheduling behavior or making claims about recovery/cleanup progress under saturation.

Only a needed scheduling policy choice gates its implementation. Missing mixed-load evidence limits operational claims, not unrelated development.

## Architectural impact and dependencies

Shared job claims/checkpoints/admission, identity cleanup, source/project erasure and low-disk handling. Update queue/cleanup sequences if the actual chosen behavior changes.

Load neighboring decisions only under these conditions:

- [PD-ARCHITECTURE-01: Select a measured supported workload and resource envelope](../../inframeld-architecture/references/decision-supported-operating-envelope.md). For measured limits and any supported latency objective.
- [PD-ACCESS-02: Keep durable work and credential lifetime explicit](../../inframeld-access-models/references/decision-admitted-work-authority.md). When checkpoint timing implements authority restrictions.

## Open questions and required evidence

- Can cleanup be admitted when ordinary work fills limits?
- Does a long job release its slot at checkpoints?
- What delay/rejection and operator action are acceptable for v1?
- What happens under restart, sustained saturation and low disk?

## Sources and finalization

- [Bounded worker mechanics](jobs-and-recovery.md#admit-work-and-claim-an-attempt).
- [Deletion obligations](../../inframeld-knowledge/references/deletion-and-retention.md).
- [Operational bounds](../../inframeld-architecture/references/runtime-deployment-and-storage.md).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
