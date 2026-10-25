# PD-RELEASES-01: Persist Deployment transitions with one shared control check

**Status:** PENDING

**Owner:** `inframeld-releases`

**Issue kind:** Implementation and concurrency contract.

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

Production serves A while B is building automatically. Alice switches Automatic to Manual and back to Automatic. An old attempt then completes. Its data may be reusable, but it must not publish through revived old authority. Bob can also promote or roll back concurrently.

The focused Deployment aggregate and valid transition rules are accepted. Exact loaded state, repository save contract and coordination among publication, mode changes and operator commands remain open. A partial aggregate or inconsistent write check could permit stale traffic changes.

## Accepted context and evidence

Preserve serving/current/previous/candidate meanings, expected revisions, control revision, newest authorized request and attempt ownership. Publication also requires current permissions and healthy complete dependencies. Canary and rollback remain Manual-only, and a candidate even at zero percent blocks Automatic mode.

An aggregate owns cohesive transition rules, while application services obtain current external facts and own transactions. Repositories do not commit or retry. Creation constructs valid first-ready state and binding, rather than loading a nonexistent Deployment. No new physical schema was selected by ADR-0079.

## Alternatives and trade-offs

1. **Load focused state and conditionally save the expected control revision.** Use a complete bounded snapshot of related serving/mode/control fields and reject mismatched versions at save. This minimizes lock lifetime but requires every competing transition to use the same predicates.
2. **Serialize the focused transition state within a short transaction.** Load the needed state under documented coordination and perform the transition/save together. This simplifies some interleavings but adds contention and requires consistent ordering with authority/dependency checks.

## Non-binding recommendation

**Proposal only.** Prefer the smallest complete state and one shared conditional control contract, using short serialization where the actual transition requires it. Choose the mechanism through publication/off-on and concurrent operator fixtures. Do not expand the aggregate to contain documents, jobs or all Pipelines.

## Decision trigger and stopping boundary

Before defining Deployment aggregate/repository state or implementing publication, mode changes, promotion, rollback or first binding.

Pause the affected state/save/concurrency contract. The focused aggregate and existing release behavior stay accepted.

## Architectural impact and dependencies

Releases state/repository/services, shared operation completion/audit, Pipeline ready results and onboarding binding. Update mode/publication/manual-transition sequence diagrams and logical record notes.

Load neighboring decisions only under these conditions:

- [PD-KNOWLEDGE-01: Finalize a complete collection selection without losing admitted input](../../inframeld-knowledge/references/decision-complete-batch-handoff.md). For complete live-input selection/handoff.
- [PD-ACCESS-06: Authorize setup details before a Deployment exists](../../inframeld-access-models/references/decision-setup-read-authority.md). For protected precreation status.
- [PD-PIPELINES-01: Capture fixed inputs and complete execution through its receipt](../../inframeld-pipelines/references/decision-execution-build-receipt-contracts.md). For captured ready-build results.

## Open questions and required evidence

- Which exact fields and dependencies must be loaded for each transition?
- What single predicate/lock protects all competing control changes?
- Which pointer/history/audit/completion effects commit together?
- How does replay recover a committed publication without changing it again?
- How are erased/unhealthy targets rejected at the final boundary?

## Sources and finalization

- [Deployment transition boundary](../../../../docs/development/pipelines-and-releases.md#deployment-transition-boundary).
- [Focused aggregate decision](../../../../docs/adr/ADR-0079-protect-deployment-transitions-with-a-focused-aggregate.md).
- [Releases records](../../../../docs/development/data-model.md#releases).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/documentation-maintenance.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
