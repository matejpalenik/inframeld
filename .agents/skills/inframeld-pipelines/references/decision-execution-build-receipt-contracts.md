# PD-PIPELINES-01: Capture fixed inputs and complete execution through its receipt

**Status:** ACCEPTED on 2026-10-29 in [ADR-0109](../../../../docs/adr/ADR-0109-capture-fixed-execution-inputs-and-commit-required-completion.md). Implementation and qualification remain separate delivery work.

**Owner:** `inframeld-pipelines`

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

Use one durable capture identity with complete bounded application-owned projections, rather than passing mutable working settings between stages or introducing another generic executor. The capture fixes Project/Pipeline, originating saved revision or ready PipelineVersion, supported explicit overrides and complete effective settings/fingerprint, exact CollectionRevisions/DocumentVersions and processing/embedding profiles, originating principal/scope, parent operation and server-owned purpose. Large inventories use immutable paged references. Connection IDs and admitted access-revision preconditions are recorded, not executable historical connection configurations or raw credentials.

Direct Pipeline queries use exact Pipeline Query authority. Evaluation uses its own run admission and protected case inputs. Live queries use exact Deployment Query authority and one actual serving selection. The owning entry operation supplies the trusted purpose/authority; callers cannot set an Evaluation/live flag to acquire another operation's permissions. These paths share ordinary retrieval/reranking/context/model execution without sharing publication or history-inspection rights.

The owning application service atomically admits the operation, required fixed capture and idempotency outcome, required audit and any initial preparation job/capacity reservation in one short transaction. Synchronous work is not forced into a background job. A no-ready-default rejection occurs before query admission and rolls back any temporary reservation. For a default-route request, recognize the original logical-route/Project/principal request before resolving a fresh current target. Replay still requires current authority and the original request meaning.

Preparation uses stable child identities and the accepted scoped IndexMaterialization contract. The capture may retain incomplete preparation progress but cannot execute with partial bindings. Atomically finalize the complete chosen prepared-binding set and eligible execution continuation under current ownership, authority and lifecycle checks. Later workers resolve the same capture, never a newer working revision or alternative numerical generation. A failed preparation leaves the capture/progress recoverable, not executable. Safe continuation preserves original inputs and only already-qualified safe work.

Readiness-only Build accepts exact authorized saved configuration and corpus from its owning caller. Explicit CLI Build supplies reviewed saved settings. A complete automatic document update supplies its Deployment-selected saved configuration. Neither uses a run ID or unsaved override as a release source. Under current authority, ownership and dependency/retention gates, finalize the complete immutable PipelineVersion, retained exact bindings, safe Build outcome, required audit and job completion together. Publication remains a separately admitted Releases operation. A successful build result cannot silently attach a candidate, move traffic or claim matching evaluation evidence when bindings differ.

For live queries, reserve answer identity and initial content-free attribution with admission before model effects. Preserve actual Deployment/revision, selected version and rollout/cohort. Before answer-generation dispatch, record the bounded exact final source-version set, including uncited sources, and the required call intent/accounting facts. Account for actual selected connection/credential observations without secrets. Direct and Evaluation work keep their own capture/run attribution and do not manufacture production-feedback receipts.

After a known valid result, validate citations and recheck current disclosure/dependency state. Commit the safe live receipt outcome, required accounting transition, original operation completion and mandatory audit before releasing a finished successful response. A required accounting transition may retain a properly attributed uncertain hold; it must not invent known zero usage. Optional diagnostic loss alone cannot fail an otherwise successful operation, but required receipt/accounting/business persistence cannot be bypassed. Network/model waits stay outside SQL transactions.

If commit acknowledgment is lost, reconcile the original saved completion. If commit cannot be established, report an honest failed or uncertain outcome and do not release a successful answer based on an unconfirmed receipt. A provider response can have succeeded while required local completion failed. Preserve known call/accounting facts without automatically calling again. No replacement answer ID, alternate model or synthetic successful receipt repairs uncertainty.

Only the first confirmed successful live response carries its transient answer body. Completed same-meaning retries return the existing authorized receipt/status with responseAvailable:false. No full production answer, question or context is copied into receipts, idempotency metadata or fallback logs. This decision adds no payload archive: active inputs and explicit Evaluation evidence use only their owning authorized retention. If original required input is unavailable, ordinary continuation is ineligible rather than reconstructed by a new model call. Client disconnect is not itself cancellation. A receipt does not prove the client received the answer.

Typed outcomes distinguish incomplete preparation, accepted work, a known completed answer or insufficient-evidence response, known failure, required-dependency unavailability, paid-dispatch uncertainty and receipt-only replay. Reuse existing operation/job states rather than adding a new state machine. Safe receipt inspection applies current principal/resource/source disclosure rules and exposes only the existing bounded attribution/outcome fields, not another caller's content or diagnostics. Direct queries and Evaluation remain excluded from production-feedback populations.

## Why and example

Alice starts a question using saved configuration 17. Bob saves configuration 18 while it runs. Separately, Production may serve a ready version using configuration 16. The application must keep each execution's chosen meaning and distinguish a ready build from permission to publish it. If an answer response is lost, a retry must not buy another answer.

Alice's captured query keeps configuration 17 while Bob saves 18. Indexing prepares the exact bindings chosen for Alice. A live question against Production instead records its actual ready version and routing cohort. If its answer is generated and the required receipt commits, but the response is lost, retry returns that receipt without the answer and without another charge. If required receipt persistence fails after generation, the result is a local failure/uncertainty, not permission to generate again.

Because stages resolve one fixed capture, concurrent edits cannot retarget the operation. Because required attribution commits before success, feedback and recovery refer to an established outcome. The cost is durable capture/progress and explicit failure handling. Passing complete immutable values everywhere could also preserve meaning, but duplicates larger messages and makes crash recovery harder. A full-answer replay cache would add a different privacy and retention contract already outside v 1.

<a id="decision-trigger-and-stopping-boundary"></a>

## Apply the accepted contract

Use this contract when the original trigger matches. Do not ask for the same policy decision again. Concrete native methods, DTO names and physical schemas are implementation choices consistent with this contract and the repository conventions. Missing measurements, fixtures or assembled evidence block the affected qualification/support claim, not authorized implementation or isolated tests. A failed test is not permission to weaken an accepted safety boundary.

<a id="open-questions-and-required-evidence"></a>

## Implementation and required evidence

Working edits during preparation, direct/Evaluation/live attribution, large binding sets, stale worker completion, failed required shards, source erasure, queue-full admission, lost preparation/Build acknowledgment, provider success followed by local persistence failure, uncertain commit, default rebinding on retry, receipt-only recovery and optional trace failure versus mandatory accounting failure. No duplicated paid calls or production feedback for direct/Evaluation runs.

These are required checks, not tests run or successful production evidence. No application edits, paid calls or production changes follow merely from recording this decision.

## Architectural impact and dependencies

Pipelines configuration/capture/build/execution, shared operations/receipts, Indexing bindings, Evaluation callers and Releases selection. Update query/build/receipt sequences and record ownership together.

Load neighboring decisions only under these conditions:

- [PD-INDEXING-01 (accepted): Exchange complete prepared bindings between Indexing capabilities](../../inframeld-indexing/references/decision-capability-binding-contracts.md). For complete prepared bindings.
- [PD-ACCESS-02 (accepted): Keep durable work and credential lifetime explicit](../../inframeld-access-models/references/decision-admitted-work-authority.md). For durable-work credential authority.
- [PD-KNOWLEDGE-01 (accepted): Finalize a complete collection selection without losing admitted input](../../inframeld-knowledge/references/decision-complete-batch-handoff.md). When consuming a complete live-input batch.

## Historical context and alternatives

The following preserves the earlier problem, context and options. Statements that a choice was open describe that earlier analysis. The approved resolution above now settles it.

<a id="problem-and-example"></a>

### Original problem and example

Historical analysis before this resolution.

Alice starts a direct query against working revision 17, then saves revision 18. Bob evaluates the captured revision while Production still serves A. A response is lost after generation. The query must retain its selected inputs, and recovery must not repeat paid generation to reconstruct the answer.

Settings/capture, builds and ordinary execution are separate accepted capabilities. Their complete input/result records, preparation handoffs and receipt admission/finalization remain to specify. Loose interfaces can follow later edits, confuse a snapshot with an executor or expose an uncommitted business result.

### Original accepted context and evidence

Historical context before this resolution. Unchanged invariants still apply.

One ordinary execution path serves direct questions, Evaluation and production. Capture exact effective configuration and corpus before preparation. Build uses authorized saved inputs, not a run ID or unsaved override. Indexing supplies verified bindings and Releases owns serving/publication.

Preserve current permissions, dependency health/pins, shared-current connection checks and paid-call uncertainty. Live answer recovery remains receipt-only, without a full-answer replay cache. Required receipt/accounting failures differ from optional trace loss. A database transaction cannot span a model wait.

### Considered alternatives and trade-offs

Historical options, resolved by the approved contract above.

1. **Pass complete fixed-input records across focused operations.** Capture once, then call preparation/execution with explicit identities and typed results. This makes boundaries visible but requires carefully owned admission and finalization steps.
2. **Pass a durable capture identity resolved by each stage.** Persist the fixed inputs and let stages load a bounded exact projection. This helps recovery and compact jobs, but adds reads and requires explicit missing/erased dependency outcomes.

## Sources and finalization

- [Pipeline operation boundary](architecture.md#pipeline-operation-boundaries).
- [Receipt-only recovery](answer-execution-and-receipts.md#answers).
- [Pipeline records](records.md#pipelines).
- [Shared ordinary execution](../../../../docs/adr/ADR-0077-separate-pipeline-settings-builds-and-answer-execution.md).

Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later change to this accepted policy. Qualification evidence must identify its artifacts, environment, failures and limits. This record does not fabricate implementation or a passing test.
