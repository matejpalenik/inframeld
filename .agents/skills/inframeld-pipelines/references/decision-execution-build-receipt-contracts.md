# PD-PIPELINES-01: Capture fixed inputs and complete execution through its receipt

**Status:** PENDING

**Owner:** `inframeld-pipelines`

**Issue kind:** Implementation and cross-module contract.

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

Alice starts a direct query against working revision 17, then saves revision 18. Bob evaluates the captured revision while Production still serves A. A response is lost after generation. The query must retain its selected inputs, and recovery must not repeat paid generation to reconstruct the answer.

Settings/capture, builds and ordinary execution are separate accepted capabilities. Their complete input/result records, preparation handoffs and receipt admission/finalization remain to specify. Loose interfaces can follow later edits, confuse a snapshot with an executor or expose an uncommitted business result.

## Accepted context and evidence

One ordinary execution path serves direct questions, Evaluation and production. Capture exact effective configuration and corpus before preparation. Build uses authorized saved inputs, not a run ID or unsaved override. Indexing supplies verified bindings and Releases owns serving/publication.

Preserve current permissions, dependency health/pins, shared-current connection checks and paid-call uncertainty. Live answer recovery remains receipt-only, without a full-answer replay cache. Required receipt/accounting failures differ from optional trace loss. A database transaction cannot span a model wait.

## Alternatives and trade-offs

1. **Pass complete fixed-input records across focused operations.** Capture once, then call preparation/execution with explicit identities and typed results. This makes boundaries visible but requires carefully owned admission and finalization steps.
2. **Pass a durable capture identity resolved by each stage.** Persist the fixed inputs and let stages load a bounded exact projection. This helps recovery and compact jobs, but adds reads and requires explicit missing/erased dependency outcomes.

## Non-binding recommendation

**Proposal only.** Prefer a durable capture identity with explicit bounded projections/results and one normal execution operation. Specify receipt admission, partial failure, finalization and commit ordering through the lost-response example. Do not invent a generic executor or full-answer cache.

## Decision trigger and stopping boundary

Before defining captured input/build/execution interfaces, preparation continuation or receipt admission/finalization.

Pause the affected interface and outcome contract. Accepted direct-query/build distinctions and receipt-only recovery are not pending.

## Architectural impact and dependencies

Pipelines configuration/capture/build/execution, shared operations/receipts, Indexing bindings, Evaluation callers and Releases selection. Update query/build/receipt sequences and record ownership together.

Load neighboring decisions only under these conditions:

- [PD-INDEXING-01: Exchange complete prepared bindings between Indexing capabilities](../../inframeld-indexing/references/decision-capability-binding-contracts.md). For complete prepared bindings.
- [PD-ACCESS-02 (accepted): Keep durable work and credential lifetime explicit](../../inframeld-access-models/references/decision-admitted-work-authority.md). For durable-work credential authority.
- [PD-KNOWLEDGE-01: Finalize a complete collection selection without losing admitted input](../../inframeld-knowledge/references/decision-complete-batch-handoff.md). When consuming a complete live-input batch.

## Open questions and required evidence

- Who commits capture, operation admission and any preparation job?
- What complete binding/result does each consumer require?
- What remains saved after preparation, dispatch, persistence or commit failure?
- Which safe receipt fields are available under current authority?
- How are direct, evaluation and live outcomes attributed without mixing feedback statistics?

## Sources and finalization

- [Pipeline operation boundary](architecture.md#pipeline-operation-boundaries).
- [Receipt-only recovery](answer-execution-and-receipts.md#answers).
- [Pipeline records](records.md#pipelines).
- [Shared ordinary execution](../../../../docs/adr/ADR-0077-separate-pipeline-settings-builds-and-answer-execution.md).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
