# ADR-0051: Use Ragas for generated tests and faithfulness evaluation

**Status:** Accepted. Supersedes [ADR-0030](ADR-0030-use-openevals-for-groundedness-evaluation.md).

**Date:** 2026-09-29

## Context and Problem Statement

Alice has a working pipeline but no evaluation cases. Asking her to write reference answers and identify exact passages in a terminal makes the first useful benchmark difficult to create. The accepted workflow now proposes cases from her permitted corpus, lets her review them, and evaluates accepted revisions explicitly.

ADR-0030 selected OpenEvals for a narrower whole-answer groundedness check. The expanded workflow needs starter synthesis and claim-level support judgments. A claim is a factual statement extracted from an answer; faithfulness measures how many evaluated claims the actual generation context supports. This differs from a boolean whole-answer judgment.

We need this capability without a hosted service, another model router, or a dataset-management product. ModelGateway must control every model call and credential. Application-owned records preserve case identity, current access, bounded evidence, and fair comparisons.

## Considered Options

- **Retain OpenEvals and add separate synthesis:** preserves the narrower integration but leaves two mechanisms and more glue for the expanded workflow.
- **Embed Ragas for synthesis and faithfulness:** covers both selected capabilities while leaving cases, passage scoring, permissions, jobs, and history in Inframeld. Default clients, mixed interfaces, and telemetry require explicit controls.
- **Build synthesis and claim judging ourselves:** gives direct control but makes a small project maintain algorithms and structured judging already available in a library.

These are architectural trade-offs, not runtime performance or quality benchmark results.

## Decision Outcome

Use **embedded Ragas** for single-passage starter generation and claim-based faithfulness. Request 20 cases by default from a frozen permitted sample of processed text, distributed across documents and sections. Explicit single-hop synthesis, personas, and keyphrase extraction replace default embedding/relationship-graph recipes for this preset.

Generated cases begin unreviewed. Default regression benchmarks contain accepted revisions only; explicit exploratory runs may include labelled unreviewed revisions. Generation, review, and evaluation are separate actions. Setup can finish without evaluation.

Select existing generator and judge connections explicitly, offering reuse without another key. No mandatory Luna/OpenAI model or implicit fallback remains. Every nested call follows `Evaluation service -> Ragas infrastructure adapter -> ModelGateway -> embedded LiteLLM -> authorized model`. Give Ragas no independent provider credentials or clients.

[Evaluation](../development/evaluation.md) owns lifecycle, passage identity/coverage, metric arithmetic, failures, and qualification. [Evaluation records](../development/data-model.md#evaluation) owns logical records, not a physical schema. [ADR-0031](ADR-0031-compare-fresh-executions-against-frozen-benchmarks.md) still requires fresh baseline/candidate runs against identical frozen inputs. Scores never authorize publication.

[ADR-0052](ADR-0052-separate-experimental-execution-from-release-ready-pipeline-builds.md) extends those execution inputs to captured working configurations (operation inputs, not an Experiment resource) before a release-ready build. It changes neither Ragas selection nor metric definitions, review rules or gateway obligations.

[ADR-0054](ADR-0054-use-shared-current-model-connections.md) keeps selected connections current. Generator/evaluator definitions select connection IDs and model settings; operations separately observe active access revisions. Changes stop further calls rather than mixing configurations or selecting old access settings. [Evaluation's consistency contract](../development/evaluation.md#connection-consistency) governs partial outcomes and comparisons; this does not change Ragas or metric definitions.

## Consequences

- One library supports the expanded workflow without requiring manual initial test authoring. Synthetic cases remain proposals, not certified ground truth or representative statistical evidence.
- Provenance must survive scenario generation. Passage expectations use source-version/artifact spans, not chunk-ID equality or fuzzy matching. Missing mappings are unscorable.
- Faithfulness is supported claims divided by evaluated claims per case, then the mean of successfully scored eligible cases. Historical OpenEvals scores retain their original meaning and cannot be reinterpreted.
- **v0.4.3 source inspection** supports the adapter design, not tested compatibility. Structured interfaces, nested constructors, asynchronous behavior, preparation cancellation, bounded retries, and intermediate capture require qualification with locked dependencies.
- Set `RAGAS_DO_NOT_TRACK=true` before import/use and disable external library exporters. Verify actual network behavior without disabling Inframeld's independently controlled tracing.
- Generated questions, references, and evidence inherit source access and erasure obligations. Immutability is not a retention or permission bypass.
- This decision adds no application implementation, dependencies, model calls, migrations, or executed calibration. Manual blank-form authoring, richer generation presets, extra judges, and external observability connectors remain deferred.

## Links

- [Superseded ADR-0030](ADR-0030-use-openevals-for-groundedness-evaluation.md), preserving its rationale.
- [Fresh comparisons ADR-0031](ADR-0031-compare-fresh-executions-against-frozen-benchmarks.md), [ModelGateway ADR-0023](ADR-0023-route-every-model-request-through-modelgateway.md), and [optional preflight ADR-0050](ADR-0050-make-model-preflight-optional-and-record-runtime-validation.md).
- [Pinned source evidence](../development/evaluation.md#gateway), [qualification still required](../development/evaluation.md#qualification), and [CLI starter-evaluation journey](https://github.com/matejpalenik/inframeld/issues/179).
- [Ragas v0.4.3 source](https://github.com/vibrantlabsai/ragas/tree/v0.4.3) and [faithfulness documentation](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/).
