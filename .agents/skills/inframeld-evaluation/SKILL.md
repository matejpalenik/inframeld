---
name: inframeld-evaluation
description: Explains and reviews Inframeld generated test cases, case review, frozen benchmarks, faithfulness, passage coverage and fresh comparisons. Use for offline evidence, not production feedback or release authority.
---

# Inframeld Evaluation

Help a developer obtain useful evidence about a Pipeline change. Evaluation owns generated cases, review, immutable revisions, benchmarks, evaluator definitions, runs, comparisons and protected results. Other owners supply source identity, processed text, ordinary execution, current permissions, model calls and release authority.

## Working model

Alice generates questions from the Support handbook, reviews them and freezes accepted case revisions into a benchmark. She compares two reranker configurations by executing both afresh against the same benchmark and evaluator. Neither side needs a newly built release version if its captured working inputs have complete verified dependencies.

A benchmark freezes case membership and revisions. An admitted run freezes effective configuration, corpus, baseline selection and bindings. Later edits do not retarget those inputs. Current access and erasure still apply, so frozen history does not mean permanently readable evidence.

Generation proposes cases. Review decides which revisions are suitable. Evaluation executes and scores them. These are separate explicit operations, and setup can finish without any of them.

## Essential rules

- Generate from a frozen permitted corpus sample across sources/sections, not only successful retrieval hits. Starter generation requests 20 single-passage cases with bounded visible shortfalls.
- Generated or edited revisions are unreviewed. Default regression membership uses accepted revisions. Exploratory unreviewed inclusion is explicit and labelled.
- Expected passages retain source version, artifact identity and coordinates. Different chunk boundaries may cover the same passage. Missing mappings are unscorable, not ordinary retrieval misses.
- Execute questions through the ordinary Pipeline without reference answers or expected evidence. Judge faithfulness only against final context actually sent to generation.
- Show denominators, failures, exclusions and paired coverage. Abstention, no claims, missing evidence and malformed judgments cannot silently become perfect scores.
- Generator/judge roles bind explicit authorized connections. All nested model work and repairs use ModelGateway, including preparation. Ragas gets no independent credentials, provider fallback or durable runner.
- Both comparison sides execute freshly. Retained snapshots do not authorize reusing historical scores or old connection access settings.
- Scores never authorize publication, pause Automatic updates or replace current permissions and retention rules.

## Explain or review

1. Start with one case Alice accepts, then edits. Identify the case revision, benchmark, captured execution input and evaluator.
2. Explain generation, review and scoring separately. For a quality claim, name the corpus, metric definition, paired population and missing observations.
3. Include changed settings, lost access, unavailable inputs or paid-call uncertainty. Preserve fixed membership without leaking protected counts.
4. Trace preparation and nested calls when reviewing gateway safety. Separate source-inspected library compatibility from executed integration and human calibration.
5. Cite the current rule. Loading this skill grants no edits, model calls, exports or releases.

Before domain-specific backend component design, code generation or structural review, read [this module's architecture](references/architecture.md) and the relevant workflow, together with Coding Standards. Its accepted design, inspected implementation and proposals have different status. Resolve a pending architectural choice before suggesting code that depends on it. Behaviour-only questions can go directly to their workflow.

## Read as needed

- For module responsibilities, collaborators, data ownership or component design/review, read [Architecture](references/architecture.md).

- For starter sampling and immutable review, read [Generation and review](references/generation-and-review.md).
- For captured inputs, baselines and fresh execution, read [Benchmarks and comparisons](references/benchmarks-and-comparisons.md).
- For passage identity, faithfulness and score interpretation, read [Metrics and evidence](references/metrics-and-evidence.md).
- For Ragas adapters, cancellation and paid work, read [Gateway and jobs](references/gateway-and-jobs.md).
- For permissions, erasure, audiences and JSONL transfer, read [History and dataset transfer](references/history-and-dataset-transfer.md).

The [Evaluation guide](../../../docs/development/evaluation.md) owns behavior. [Evaluation records](../../../docs/development/data-model.md#evaluation) defines logical records without mandating one physical table per concept. Exact runtime and wire qualification remains explicit.
