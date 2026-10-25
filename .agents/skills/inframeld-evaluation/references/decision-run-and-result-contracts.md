# PD-EVALUATION-02: Coordinate fixed runs and expose honest protected results

**Status:** PENDING

**Owner:** `inframeld-evaluation`

**Issue kind:** Implementation and evidence contract.

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

Alice compares configurations P1 and P2 over 20 frozen cases. One answer fails, one expected passage has no compatible mapping and Bob loses source access before inspecting the results. The comparison must retain its original population without presenting missing pairs as improvements or leaking protected case counts.

The comparison semantics and honest denominators are selected. Exact captured run inputs, child progress, per-metric outcomes and protected-read representations remain open. An overbroad “success/score” result cannot express a valid execution with an unscorable metric or a partially unavailable paired comparison.

## Accepted context and evidence

Both sides run freshly through ordinary Pipelines with fixed benchmark/evaluator/configuration/corpus inputs. Reference answers and expected passages never enter the tested execution. Execution success differs from metric eligibility. Current access and erasure govern historical results.

Preserve missing pairs, failures, exclusions and original permitted scope. No automatic winner, publication permission or reuse of historical scores follows. Shared-current connection changes retain their exact admission/dispatch rules. Durable progress uses existing jobs rather than a separate evaluation runner.

## Alternatives and trade-offs

1. **Use explicit per-case/per-metric outcomes with bounded progress.** Record actual execution and scoring outcomes separately, then compute summaries over named populations. This supports honest recovery and denominators, but needs carefully scoped protected projections.
2. **Expose a run summary backed by exact retained child evidence.** Keep the public summary compact while retaining typed detailed evidence behind authorized reads. This is easier for clients, but only works if missing/unscorable reasons and denominators remain explicit rather than hidden.

## Non-binding recommendation

**Proposal only.** Prefer explicit internal child/metric outcomes with bounded summary and detail projections. Define which facts are safe to expose after access changes. The two approaches can cooperate, but the complete contract must be reviewed before choosing record/wire shapes.

## Decision trigger and stopping boundary

Before defining run/comparison inputs, durable progress, scoring outcomes, result inspection or summary/export schemas.

Pause the affected run/result interface. Honest denominators, fresh execution and current access are accepted requirements.

## Architectural impact and dependencies

Evaluation coordinator/scorers, Pipeline caller contracts, shared jobs, protected history and comparison presentation. Update preparation/execution/scoring/history sequences together.

Load neighboring decisions only under these conditions:

- [PD-PIPELINES-01: Capture fixed inputs and complete execution through its receipt](../../inframeld-pipelines/references/decision-execution-build-receipt-contracts.md). For ordinary execution/capture results.
- [PD-INDEXING-03: Keep source passage identity stable when chunking changes](../../inframeld-indexing/references/decision-source-coordinates.md). For canonical passage identity.
- [PD-ACCESS-02: Keep durable work and credential lifetime explicit](../../inframeld-access-models/references/decision-admitted-work-authority.md). For admitted background-work authority.

## Open questions and required evidence

- What inputs freeze at admission and which current facts are rechecked?
- How are incomplete children recovered without repeating uncertain paid work?
- What exact denominator accompanies each metric and paired comparison?
- What can a caller learn when some captured sources are now inaccessible?
- How are unscorable coordinates distinguished from retrieval misses?

## Sources and finalization

- [Comparison and protected history](../../../../docs/development/evaluation.md).
- [Remaining Evaluation contracts](../../../../docs/development/evaluation.md#evaluation-operation-boundaries).
- [Evaluation records](../../../../docs/development/data-model.md#evaluation).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/documentation-maintenance.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
