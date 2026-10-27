# PD-EVALUATION-03: Qualify embedded Ragas without hidden calls or false confidence

**Status:** PENDING

**Owner:** `inframeld-evaluation`

**Issue kind:** Adapter contract and model-quality qualification.

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

Alice generates starter cases, then scores an answer containing one unsupported numerical claim. A nested library transform might call an embedding or judge unexpectedly, while a missed claim can make faithfulness look perfect. Both the call path and the measurement need evidence.

Ragas and the selected roles are accepted. Source-inspected compatibility does not qualify actual integration, nested call control or judge accuracy. Concrete adapter contracts and numeric calibration acceptance thresholds remain unfinished.

## Accepted context and evidence

Ragas is embedded behind application adapters, not a durable runner. Every synthesis, judge, extraction and repair uses ModelGateway with explicit selected connections and bounds. Starter generation permits zero generation-time embedding calls. Unexpected library work must fail before unauthorized dispatch.

Faithfulness judges claims against final supplied context. Calibration uses human-labelled evidence, separate extraction/classification error and held-out examples. Preserve abstention, no-claim and malformed/unavailable outcomes. No score authorizes release, and no automatic model fallback repairs failed qualification.

## Alternatives and trade-offs

1. **Start with narrowly qualified library adapters and fixtures.** Implement only supported library paths, assert their actual outbound work through gateway doubles/private test adapters, then calibrate the chosen judge. This controls scope but exposes unsupported paths as explicit failures.
2. **Integrate the broader selected flow before qualification.** Exercise the complete library graph with strict dispatch interception and bounded workloads, then narrow unsupported paths. This can reveal integration interactions earlier but costs more and must not permit hidden paid calls.

## Non-binding recommendation

**Proposal only.** Prefer narrow supported adapters with meaningful call/cancellation/failure fixtures, followed by human calibration of the actual rubric. Select thresholds from the reviewed labelled evidence, not the old whole-answer agreement target. This task makes no model call or threshold commitment.

## Decision trigger and stopping boundary

Before implementing embedded generator/judge adapters or claiming supported model-quality/calibration results.

Unresolved adapter/metric contracts require discussion. Calibration remains a claim/release gate, not a reason to block authorized isolated integration tests.

## Architectural impact and dependencies

Evaluation library adapters, ModelGateway role/accounting paths, case generation and faithfulness evidence. Update nested-call sequences and calibration documentation, without adding a hosted evaluator service.

Load neighboring decisions only under these conditions:

- [PD-CONTRACTS-01: Enforce model policy on the actual outbound path](../../inframeld-application-contracts/references/decision-gateway-enforcement.md). For supported dispatch/adapter contracts.
- [PD-CONTRACTS-02: Coordinate budget policy, reservations and uncertain settlement](../../inframeld-application-contracts/references/decision-spending-coordination.md). For bounded paid calls and uncertain holds.

## Open questions and required evidence

- Which pinned library paths and transforms are supported?
- How are hidden retries, embedding calls and late callbacks prevented?
- Which labelled corpus/rubric and numeric thresholds qualify extraction and support classification?
- How are repeated borderline/adversarial results retained without favorable selection?

## Sources and finalization

- [Ragas integration and calibration](generation-and-review.md).
- [Selected Ragas decision](../../../../docs/adr/ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md).
- [All model requests share the gateway](../../../../docs/adr/ADR-0023-route-every-model-request-through-modelgateway.md).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
