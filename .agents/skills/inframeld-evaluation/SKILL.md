---
name: inframeld-evaluation
description: Explain or review Inframeld pipeline test cases, frozen benchmarks, OpenEvals groundedness, ModelGateway judge integration, baseline/candidate comparisons and evaluation history. Use for offline evaluation semantics; online answer feedback is owned by Pipelines.
---

# Inframeld Evaluation

Help a developer interpret evidence about a pipeline change. Evaluation owns cases, frozen benchmarks, evaluator revisions, runs, comparisons, and bounded review evidence. Serving pointers, document permissions, and production answer feedback have other owners.

## Scope and reading route

Default to read-only guidance. Loading this skill authorizes no code edit, model call, export, or release. Read only relevant sections, cite them, and distinguish accepted design, proposed qualification, and observed implementation.

- [Evaluation](../../../docs/development/evaluation.md) owns metrics, denominators, calibration, cost observations, and evidence limits. [Evaluation records](../../../docs/development/data-model.md#evaluation) defines cases, snapshots, runs, and results.
- [ADR-0030](../../../docs/adr/ADR-0030-use-openevals-for-groundedness-evaluation.md) explains OpenEvals; [ADR-0031](../../../docs/adr/ADR-0031-compare-fresh-executions-against-frozen-benchmarks.md) explains fresh comparisons against frozen benchmarks.
- [Model connections](../../../docs/development/model-connections.md) owns ModelGateway and judge credentials; [Access control](../../../docs/development/access-control.md) owns current permissions; [Jobs](../../../docs/development/jobs-and-idempotency.md) owns retries and uncertainty.
- For comparability, read [pipeline bindings](../../../docs/development/data-model.md#pipelines) and [Indexing](../../../docs/development/indexing.md). For publication read [Pipelines and Releases](../../../docs/development/pipelines-and-releases.md); for online evidence read [Answer feedback](../../../docs/development/answer-feedback.md); for erasure read [Retention and deletion](../../../docs/development/retention-and-deletion.md).
- [Maintainer checks](../../../docs/development/evaluation.md#maintainer-checks) summarize comparison, history, and judge-boundary scenarios.

- For an edited test, follow [frozen comparison inputs](../../../docs/development/evaluation.md#comparison) → [retained history and comparability](../../../docs/development/evaluation.md#history). Read [qualification](../../../docs/development/evaluation.md#qualification) before making quality claims.

## Essential boundaries

A TestCase has a stable pipeline-associated identity and editable current content. A BenchmarkRevision freezes ordered case IDs and exact content. An EvaluatorRevision freezes rubric/library, metrics, judge, and output contract. An EvaluationRun executes one exact PipelineVersion under those snapshots and an effective access scope. A comparison references baseline and candidate runs. These concepts do not mandate one aggregate or repository per revision, metric, or score.

OpenEvals and configurable GPT-6 Luna are selected for initial groundedness qualification. Do not silently substitute a model or reopen the comparison without a concrete blocker. The library does not supply Inframeld’s case management, frozen snapshots, durable runs, paired views, history, or access controls.

Explicit Compare freezes baseline/candidate, benchmark/evaluator, and access conditions, then executes both ready versions afresh through the normal query path. A build or edited prompt does not secretly run a judge. Later case edits leave old inputs intact. Changed questions, rubric, or incompatible access prevent a like-for-like improvement claim. Label deliberate corpus changes; a matching remote model alias does not prove unchanged implementation.

Every model call, including nested, repair, and embedding calls, goes through ModelGateway. The OpenEvals model-client facade is bound to admitted settings and receives no independent credentials. Disable tracing/export and qualify actual network behavior; a custom type alone does not prove this boundary.

Judge against the exact final generation context after reranking/truncation. The boolean verdict plus explanation measures support under its rubric, not truth, completeness, relevance, or a fraction of extracted claims. Preserve the documented basic-fact/calculation allowance. Invalid, truncated, or refused output is a failure, not a negative quality vote. Require actual booleans, not truthy strings. Explicit abstention is not-applicable for groundedness; empty evidence does not earn a perfect score.

Keep source-hit, citation identity/presence, groundedness, outcome, latency, and usage separate. Show denominators, failures, skips, and paired coverage. Never discard failed candidate cases to claim improvement. Retain bounded answers/final evidence and provenance without secrets or unbounded traces; recheck current permissions on history. Erased or expired evidence is unavailable.

Scores and feedback never authorize releases. Compare remains explicit in both modes and does not pause Automatic updates. Use Manual releases when the endpoint must remain fixed during review. Automatic publication has no hidden judge. Initial onboarding needs no test cases or judge configuration. Exporters, LangSmith/Langfuse, custom evaluator platforms, and deeper automatic diagnosis/remediation remain deferred.

## Explain and review

For “P13 is better than P12,” identify benchmark/evaluator, corpus variable, access scope, valid paired cases, and failures. For an edited question, follow the stable case ID to its old frozen content. For gateway review, trace actual library calls, repairs, budgets, and telemetry. Use the guide’s human-labelled calibration and repeatability plan without claiming it has run. A small benchmark is evidence about those cases, not a production guarantee.
