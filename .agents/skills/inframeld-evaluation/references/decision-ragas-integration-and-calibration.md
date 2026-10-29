# PD-EVALUATION-03: Qualify embedded Ragas without hidden calls or false confidence

**Status:** ACCEPTED on 2026-10-29 in [ADR-0115](../../../../docs/adr/ADR-0115-qualify-narrow-ragas-paths-and-claim-level-judge-evidence.md). Implementation and qualification remain separate delivery work.

**Owner:** `inframeld-evaluation`

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Contents

- [Approved resolution](#approved-resolution)
- [Why and example](#why-and-example)
- [Implementation and required evidence](#implementation-and-required-evidence)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Historical context and alternatives](#historical-context-and-alternatives)
- [Sources and finalization](#sources-and-finalization)

<a id="non-binding-recommendation"></a>

## Approved resolution

Start with the already source-inspected Ragas 0.4.3 interfaces and lock the complete compatible dependency set during implementation. Support the explicit single-passage/single-hop starter synthesizer over application-selected processed evidence, gateway-bound structured LLM/keyphrase preparation, and claim extraction/support classification for faithfulness. No default transform graph, persona generation, multi-hop synthesis, relationship graph or generation-time embeddings is enabled. Library/version changes require the same adapter and fixture qualification, not silent compatibility assumptions.

Explicitly construct every nested supported LLM/embedding interface through the existing application gateway adapters. Give Ragas no provider key, independent provider client, arbitrary destination or analytics/exporter capability. Set its tracking opt-out before import. Unsupported constructors/transforms and unbound paths fail before egress. Hidden SDK/library retries, schema repairs and provider fallbacks are disabled in the initial profile. Each known malformed unit fails visibly. Cancellation, deadline, current authority/access revision and spending apply before each nested call, including preparation before a final executor handle exists. Late callbacks retain their original fence and cannot publish after ownership loss.

The initial plan permits at most one selected-passage keyphrase-preparation call and one synthesis call per requested generation unit, and at most one claim-extraction plus one support-classification call per answered scoring unit. Reuse already completed preparation only with matching exact inputs and recorded provenance. At most 100 factual claims are scored per answer; larger extraction fails/unscorable rather than silently dropping claims. All possible calls appear in the bounded plan and reservation/cost review. Missing or malformed usage preserves holds under the gateway contract. No automatic paid repair follows.

Use a versioned human-labelled gold corpus for the exact rubric, context and claim boundaries. Qualification requires at least 50 answers and 200 atomic factual claims, including at least 50 unsupported claims and each required adversarial category: contradiction, numbers, negation, prompt injection, long context, irrelevant-but-supported text, abstention and no evidence/claim. Hold out at least 20 answers and 100 claims by source/document family, including at least 25 supported and 25 unsupported claims, unused for tuning. Record provenance and disputed labels; do not count an agent's unreviewed synthetic labels as human truth. Existing externally human-annotated data may contribute when rights and exact claim alignment are established; word-span labels alone do not prove complete atomic-claim extraction.

Selected engineering gates on the untouched held-out set are claim-extraction precision and recall each at least 0.95, unsupported critical number/negation/contradiction claim recall at least 0.95, support-classification balanced accuracy at least 0.90, and unsupported claims incorrectly labelled supported no more than 0.05. Report raw counts, class-specific errors and uncertainty; these thresholds are chosen acceptance criteria, not measured results or a universal accuracy promise. Preserve the existing five fixed borderline/adversarial examples run three times each. Retain every repeat, failure and cost. No known unsupported critical claim may disappear or be marked supported in any repeat; per-example score spread above 0.10 fails the initial stability gate.

Missing gold data, failed thresholds or unexecuted integration leaves the adapter/judge unqualified. Functional implementation and isolated tests may proceed. Any explicitly requested exploratory score is labelled uncalibrated and cannot be sold as a qualified quality result. Ordinary queries, Build and first publication need no judge. Recalibrate after material library/model/prompt/rubric/language changes. Never change the judge, lower thresholds or select favorable repeats automatically to pass. This resolves policy now without fabricating human review or paid test evidence.

## Why and example

A judging model can produce valid JSON and still miss an unsupported claim. A narrow adapter and explicit human-labelled checks make the limits inspectable.

Bob's answer adds an unsupported refund amount. The calibration checks whether the judge extracted that claim and whether it correctly rejected it. Missing the claim cannot produce a trustworthy perfect score.

The initial supported flow is deliberately small. Human-labelled evidence and authorized model tests still need to exist before anyone claims the judge is calibrated.

<a id="decision-trigger-and-stopping-boundary"></a>

## Apply the accepted contract

Use this contract when the original trigger matches. Do not ask for the same policy decision again. Concrete native methods, DTO names and physical schemas are implementation choices consistent with this contract and the repository conventions. Missing measurements, fixtures or assembled evidence block the affected qualification/support claim, not authorized implementation or isolated tests. A failed test is not permission to weaken an accepted safety boundary.

<a id="open-questions-and-required-evidence"></a>

## Implementation and required evidence

Pinned adapter paths, no hidden calls/embeddings/retries, early cancellation, late callbacks, malformed output, held-out extraction/classification metrics and all fixed repeats. No paid calibration run is authorized by documentation.

These are required checks, not tests run or successful production evidence. No application edits, paid calls or production changes follow merely from recording this decision.

## Architectural impact and dependencies

Evaluation library adapters, ModelGateway role/accounting paths, case generation and faithfulness evidence. Update nested-call sequences and calibration documentation, without adding a hosted evaluator service.

Load neighboring decisions only under these conditions:

- [PD-CONTRACTS-01 (accepted): Enforce model policy on the actual outbound path](../../inframeld-application-contracts/references/decision-gateway-enforcement.md). For supported dispatch/adapter contracts.
- [PD-CONTRACTS-02 (accepted): Coordinate budget policy, reservations and uncertain settlement](../../inframeld-application-contracts/references/decision-spending-coordination.md). For bounded paid calls and uncertain holds.

## Historical context and alternatives

The following preserves the earlier problem, context and options. Statements that a choice was open describe that earlier analysis. The approved resolution above now settles it.

<a id="problem-and-example"></a>

### Original problem and example

Historical analysis before this resolution.

Alice generates starter cases, then scores an answer containing one unsupported numerical claim. A nested library transform might call an embedding or judge unexpectedly, while a missed claim can make faithfulness look perfect. Both the call path and the measurement need evidence.

Ragas and the selected roles are accepted. Source-inspected compatibility does not qualify actual integration, nested call control or judge accuracy. Concrete adapter contracts and numeric calibration acceptance thresholds remain unfinished.

### Original accepted context and evidence

Historical context before this resolution. Unchanged invariants still apply.

Ragas is embedded behind application adapters, not a durable runner. Every synthesis, judge, extraction and repair uses ModelGateway with explicit selected connections and bounds. Starter generation permits zero generation-time embedding calls. Unexpected library work must fail before unauthorized dispatch.

Faithfulness judges claims against final supplied context. Calibration uses human-labelled evidence, separate extraction/classification error and held-out examples. Preserve abstention, no-claim and malformed/unavailable outcomes. No score authorizes release, and no automatic model fallback repairs failed qualification.

### Considered alternatives and trade-offs

Historical options, resolved by the approved contract above.

1. **Start with narrowly qualified library adapters and fixtures.** Implement only supported library paths, assert their actual outbound work through gateway doubles/private test adapters, then calibrate the chosen judge. This controls scope but exposes unsupported paths as explicit failures.
2. **Integrate the broader selected flow before qualification.** Exercise the complete library graph with strict dispatch interception and bounded workloads, then narrow unsupported paths. This can reveal integration interactions earlier but costs more and must not permit hidden paid calls.

## Sources and finalization

- [Ragas integration and calibration](generation-and-review.md).
- [Selected Ragas decision](../../../../docs/adr/ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md).
- [All model requests share the gateway](../../../../docs/adr/ADR-0023-route-every-model-request-through-modelgateway.md).

Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later change to this accepted policy. Qualification evidence must identify its artifacts, environment, failures and limits. This record does not fabricate implementation or a passing test.
