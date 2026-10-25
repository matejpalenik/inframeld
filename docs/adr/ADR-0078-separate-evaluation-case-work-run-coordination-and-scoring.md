# ADR-0078: Separate Evaluation case work, run coordination and scoring

**Status:** Accepted

**Date:** 2026-10-25

## Context and Problem Statement

Alice generates cases, reviews revisions and compares two configurations. Case editing/review, long-running execution, scoring and protected result inspection have different authority and state. Existing behavior freezes inputs and requires ordinary Pipeline execution, but the internal application boundary was open.

## Considered Options

- One Evaluation service manages cases, runs, scoring and history. This gives a simple initial entry point but collects unrelated authority, state and provider lifetimes.
- Focused case generation/review operations, run/comparison coordination and scoring adapters exchange explicit progress/result contracts. This makes ownership visible while requiring more careful handoffs. This is selected.

## Decision Outcome

Evaluation separates case generation/review operations, run/comparison coordination and scoring adapters. Generation, review and evaluation remain distinct explicit product operations. Evaluation asks Pipelines to execute ordinary questions with fixed inputs, then scores actual outcomes and permitted evidence. Reference answers and expected passages remain outside that execution.

Ragas remains an embedded library behind adapters. Existing durable jobs own controlled progress, and every remote synthesis/judge/repair request uses ModelGateway. Keep execution success separate from per-metric scoring eligibility, preserve benchmark membership and expose results only under their current protected-read contracts. Scores supply evidence rather than publication authority.

## Consequences

Specify exact case/run inputs, per-metric outcomes, protected result representations, bounded progress and preparation/execution/scoring coordination before implementing the ports or persistence. No generic Dataset/Experiment platform, new runner or table per concept follows from this split. Runtime integration, library compatibility and human judge calibration remain qualification work.

This records accepted target architecture. Implementation and qualification remain unfinished. Existing product decisions remain authoritative, and no earlier ADR is superseded.

## Links

- [Current owning guide and remaining design](../development/evaluation.md#evaluation-operation-boundaries).
- [Logical records](../development/data-model.md#evaluation).
- [Module architecture](../../.agents/skills/inframeld-evaluation/references/architecture.md).
- [Application/component conventions](../development/application-structure.md#component-conventions) and [modular-backend decision](ADR-0001-use-one-modular-backend-with-clear-domain-boundaries.md).
