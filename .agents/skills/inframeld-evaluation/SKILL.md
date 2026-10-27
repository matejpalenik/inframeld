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

For backend component design, code generation or structural review, read [module architecture](references/architecture.md), the affected workflow and Coding Standards. Behavior-only questions go directly to their workflow. Pending proposals do not authorize dependent code.

## Pending decisions for affected work

Load only matching triggers. Discuss and obtain approval before code depends on an unresolved choice, following [decision finalization](../../../docs/development/guides/architecture-decisions.md). Unrelated decisions do not block work. Qualification gaps gate claims, not evidence-gathering tests.

- [PD-EVALUATION-01](references/decision-case-review-contracts.md): Before implementing case generation/review commands, revision preconditions, local acceptance or their public result contracts.
- [PD-EVALUATION-02](references/decision-run-and-result-contracts.md): Before defining run/comparison inputs, durable progress, scoring outcomes, result inspection or summary/export schemas.
- [PD-EVALUATION-03](references/decision-ragas-integration-and-calibration.md): Before implementing embedded generator/judge adapters or claiming supported model-quality/calibration results.

## Read as needed

Choose the row matching the task. Workflow, contract and architecture views are separate reading units. Do not load this whole table.

| Task | Direct reference |
| --- | --- |
| Module/component design or structural review | [Evaluation architecture: compare fixed inputs with honest evidence](references/architecture.md) |
| Benchmarks and comparisons | [Freeze inputs and compare fresh executions](references/benchmarks-and-comparisons.md) |
| Case audiences | [Protect evaluation cases and imported content](references/case-audiences.md) |
| Faithfulness | [Judge support in the actual final context](references/faithfulness.md) |
| Gateway and jobs | [Integrate Ragas through the existing gateway and jobs](references/gateway-and-jobs.md) |
| Generation and review | [Generate starter cases and review exact revisions](references/generation-and-review.md) |
| History and dataset transfer | [Protect case history and transfer datasets deliberately](references/history-and-dataset-transfer.md) |
| Judge calibration | [Qualify and calibrate the selected judge](references/judge-calibration.md) |
| Metrics and evidence | [Explain what a score actually measures](references/metrics-and-evidence.md) |
| Passage coverage | [Measure complete expected-passage coverage](references/passage-coverage.md) |
| Logical records and representation ownership | [Evaluation inputs, revisions and observations](references/records.md) |

## Source ownership

Focused references own accepted behavior and logical design. Code, generated OpenAPI and migrations own implemented representations. Read exact definitions when fields matter, ADRs for rationale or conflicts, and matching pending decisions before dependent design. Human guides own development procedures.
