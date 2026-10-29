# ADR-0115: Qualify narrow Ragas paths and claim-level judge evidence

**Status:** Accepted

**Date:** 2026-10-29

## Context and Problem Statement

A judging model can produce valid JSON and still miss an unsupported claim. A narrow adapter and explicit human-labelled checks make the limits inspectable.

## Considered Options

- Use the focused bounded contract above. Selected.
- Enable broader default library transforms before qualification, increasing hidden-call and calibration risk.

## Decision Outcome

Apply the [complete accepted PD-EVALUATION-03 contract](../../.agents/skills/inframeld-evaluation/references/decision-ragas-integration-and-calibration.md#approved-resolution). It owns the exact behavior, bounds, current-state checks and failure outcomes. Start with the already source-inspected Ragas 0.4.3 interfaces and lock the complete compatible dependency set during implementation. Support the explicit single-passage/single-hop starter synthesizer over application-selected processed evidence, gateway-bound structured LLM/keyphrase preparation, and claim extraction/support classification for faithfulness. No default transform graph, persona generation, multi-hop synthesis, relationship graph or generation-time embeddings is enabled. Library/version changes require the same adapter and fixture qualification, not silent compatibility assumptions.

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Consequences

The initial supported flow is deliberately small. Human-labelled evidence and authorized model tests still need to exist before anyone claims the judge is calibrated.

Bob's answer adds an unsupported refund amount. The calibration checks whether the judge extracted that claim and whether it correctly rejected it. Missing the claim cannot produce a trustworthy perfect score.

Implementation, measured support and qualification remain separate. A chosen threshold is not a measured result. No application code, public endpoint or passing runtime evidence is delivered here.

## Links

- [Owning contract](../../.agents/skills/inframeld-evaluation/references/decision-ragas-integration-and-calibration.md#approved-resolution)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
