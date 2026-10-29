# ADR-0114: Freeze evaluation runs and report per-metric populations

**Status:** Accepted

**Date:** 2026-10-29

## Context and Problem Statement

A run can answer successfully while a metric cannot be calculated. A comparison can also have missing pairs. Those facts must remain visible instead of collapsing into one success flag or score.

## Considered Options

- Use the focused bounded contract above. Selected.
- Expose only a run score, hiding distinct failures, unscorable metrics and missing pairs.

## Decision Outcome

Apply the [complete accepted PD-EVALUATION-02 contract](../../.agents/skills/inframeld-evaluation/references/decision-run-and-result-contracts.md#approved-resolution). It owns the exact behavior, bounds, current-state checks and failure outcomes. Admit an explicit run with fixed Project/Pipeline, benchmark and case revisions/review states, evaluator/rubric/schema/metric revisions, exact PipelineVersion or captured execution identity, corpus/profiles/prepared bindings, model connection/settings and access-revision preconditions, initiating principal/scope, budget/deadline and stable child identities. Use the existing durable jobs and one ordinary Pipeline execution path. A comparison owns two freshly admitted runs over the same frozen benchmark/evaluator and source scope. Resolve a live baseline once, never per case. Initial runs contain at most 200 cases per side. Two comparison sides may be scheduled under the supported global limits, without another execution engine.

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Consequences

The result model is more explicit, but readers can distinguish a retrieval problem, a judge problem and an incomplete experiment. Access changes may make an old full summary unavailable.

Alice runs 20 cases. Nineteen answers finish and one expected passage cannot be mapped. The summary shows the failed execution and unscorable metric separately; it does not pretend every result came from 20 complete pairs.

Implementation, measured support and qualification remain separate. A chosen threshold is not a measured result. No application code, public endpoint or passing runtime evidence is delivered here.

## Links

- [Owning contract](../../.agents/skills/inframeld-evaluation/references/decision-run-and-result-contracts.md#approved-resolution)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
