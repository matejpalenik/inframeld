---
name: inframeld-evaluation
description: Explain or review Inframeld pipeline test cases, frozen benchmarks, OpenEvals groundedness, ModelGateway judge integration, baseline/candidate comparisons and evaluation history. Use for offline evaluation semantics; online answer feedback is owned by Pipelines.
---

# Inframeld Evaluation

Help the developer provide quick, useful evidence about a pipeline change.
Evaluation owns test cases, benchmark/evaluator snapshots, runs, case results,
comparisons and bounded evaluation evidence. It does not own serving pointers,
source permissions or production answer feedback.

## Scope and authoritative sources

Default to read-only assistance; loading this skill authorizes no code edit,
model call, external export or release. Resolve paths from the repository root.
Start with the guide's evaluation explanation and only the relevant owning ADR.

- `docs/ARCHITECTURE.md` explains the in-app experience and evidence limits.
- `docs/adr/ADR-0009-deterministic-evaluation-and-release-decisions.md` owns the
  complete evaluation model, rubric, adapter and qualification requirements.
- `docs/adr/ADR-0007-byok-provider-boundary.md` owns ModelGateway; ADR-0008 owns
  job/retry behavior and ADR-0006 current authorization.
- ADR-0004/0016 explain exact version bindings when comparability is in question;
  ADR-0010 owns publication/release authority; ADR-0018 owns online feedback.
- ADR-0015 governs evidence deletion. ADR-0020's first-answer experience must
  not require test creation, an evaluation run or judge-model configuration.

## Language and consistency boundaries

A TestCase has a stable pipeline-associated identity and editable current content.
A BenchmarkRevision freezes ordered case IDs and exact content. An
EvaluatorRevision freezes the rubric/library, metrics, judge and output contract.
An EvaluationRun evaluates one exact PipelineVersion under those snapshots and
an effective access scope. A comparison references baseline and candidate runs.
Case results record outcomes, metrics and evidence, including failures.

The pipeline benchmark's edit/freeze operation and run publication are conceptual
consistency boundaries. Case revisions can be embedded in a frozen full snapshot;
do not mandate a separate aggregate/repository per revision, metric or score.
These are planned domain concepts, not claims about implemented symbols.

## Decisions to preserve

1. OpenEvals supplies maintained holistic groundedness evaluation. Configurable
   GPT-5.6 Luna is the baseline judge to qualify. Do not reopen the framework
   comparison absent a concrete blocker or silently substitute another model.
2. Inframeld owns pipeline-associated case CRUD, frozen benchmark snapshots,
   durable execution, paired views, history and access. Choosing a metric
   library does not supply these product features.
3. Explicit Compare freezes baseline/candidate, one benchmark/evaluator and
   access scope, then performs fresh execution of both ready versions through
   the normal query path. Editing a prompt/test or finishing a build does not
   silently run a judge or change traffic.
4. Later case edits never rewrite old run inputs. Changed questions/rubric or
   incompatible access invalidate a like-for-like improvement claim. Label a
   deliberate corpus change. Matching a model alias does not prove its remote
   implementation has remained unchanged.
5. Every model call traverses ModelGateway, including nested/repair/embedding
   calls. The OpenEvals explicit model-client facade is bound to the admitted
   connection/settings; it receives no independent credentials. Disable
   tracing/export and test actual network behavior. A custom-model type alone
   is not proof the boundary works.
6. Judge the generated answer against the exact final generation context, after
   reranking/truncation. OpenEvals's boolean verdict plus explanation measures
   support under its rubric, not truth, completeness, relevance or a percentage
   of extracted claims. Its allowance for basic facts/calculation is explicit.
7. Invalid, truncated or refused judge outputs are failures, not negative
   quality verdicts; accept actual booleans, not truthy strings. Explicit
   abstention is not-applicable for groundedness and visible as an outcome.
   Do not turn empty evidence into a perfect score.
8. Retrieval source-hit, citation identity/presence, groundedness, outcomes and
   latency/usage remain distinct signals. Show denominators, failed/skipped
   counts and paired coverage. Never drop failed candidate cases to claim a win.
9. Store bounded answers/final evidence and provenance needed for case review;
   exclude secrets and unbounded traces. Recheck current permissions on history.
   Erased/expired evidence is unavailable, not mysteriously reproducible.
10. Neither scores nor feedback authorize a release. Comparisons are explicit
    in both publication modes and freeze exact versions; they do not pause
    Automatic updates. Use Manual releases for a fixed endpoint during review.
    Automatic publication is authorized by the source/configuration action,
    never by a metric, and runs no hidden judge. LangSmith, Langfuse,
    exporters, custom evaluator platforms and deeper diagnosis/remediation are
    deferred. Preserve application-owned evidence/read contracts, not an unused
    exporter or autonomous optimization framework.

## Task examples and qualification

For “P13 scores better than P12,” identify the exact benchmark/evaluator, corpus
variable, effective access, valid paired cases and failures before describing
improvement. For “a changed question lost its history,” trace the stable case ID
to its frozen old content and results. For gateway review, follow every actual
library call/repair path and check budgets, retries and disabled telemetry.

Use the bounded human-labelled calibration and repeatability tests in ADR-0009;
distinguish a proposed threshold from measured accuracy. A small benchmark is
feedback about those cases, not a production guarantee. Read the neighboring
release/access rule when relevant without loading all domain skills.
