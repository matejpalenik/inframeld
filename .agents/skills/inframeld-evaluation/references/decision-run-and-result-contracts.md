# PD-EVALUATION-02: Coordinate fixed runs and expose honest protected results

**Status:** ACCEPTED on 2026-10-29 in [ADR-0114](../../../../docs/adr/ADR-0114-freeze-evaluation-runs-and-report-per-metric-populations.md). Implementation and qualification remain separate delivery work.

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

Admit an explicit run with fixed Project/Pipeline, benchmark and case revisions/review states, evaluator/rubric/schema/metric revisions, exact PipelineVersion or captured execution identity, corpus/profiles/prepared bindings, model connection/settings and access-revision preconditions, initiating principal/scope, budget/deadline and stable child identities. Use the existing durable jobs and one ordinary Pipeline execution path. A comparison owns two freshly admitted runs over the same frozen benchmark/evaluator and source scope. Resolve a live baseline once, never per case. Initial runs contain at most 200 cases per side. Two comparison sides may be scheduled under the supported global limits, without another execution engine.

Keep execution and scoring as distinct typed per-case observations. Execution distinguishes answer, explicit insufficient-evidence abstention, failure, cancellation, uncertainty and unattempted work. Each metric independently records eligibility, success/value/denominator, unscorable reason, failure or not-attempted status. Preserve actual stage-specific evidence, citations, claim/verdicts, safe call attribution, latency and known/estimated/unknown usage in bounded protected artifacts. Expected passages/reference answers never enter tested retrieval/generation or extra faithfulness context.

Checkpoint original child outcomes. On recovery, do not repeat completed Pipeline or judge work. A known saved answer may be scored later only through an explicitly eligible original continuation. An uncertain paid call stays uncertain and cannot be redispatched merely because no observation was saved. Required original inputs unavailable/erased or relevant shared access changes stop remaining affected dispatches. A newly selected evaluator, source scope or current connection context requires fresh explicit admission; both comparison sides must be run freshly for a new like-for-like claim.

Compute passage coverage separately at retrieval, selection and final context: Found divided by mappable eligible cases, with original admitted, eligible, failed, excluded, not-found and unscorable counts. Faithfulness is supported-claim fraction for each eligible scored answer and a macro mean across those answers; no-claim, abstention and invalid judge outcomes keep their distinct rules. Citation presence/validity, execution completion, latency and spending keep their own named populations. Zero denominator is no numeric score, not zero quality or perfect quality.

Pair comparisons by exact case revision and named metric. Report both full run populations, intersection of comparable scored pairs, missing pairs and reasons. Calculate differences only on that explicit paired population and disclose reduced coverage. No automatic winner, significance claim from a tiny sample, historical-score substitution or release authority follows.

Summary/detail/export are bounded paginated projections of saved facts, never read-triggered Pipeline/judge work. Recheck current run-inspection authority, case audiences and every source implicated by a returned artifact. If any captured case population is now inaccessible, deny the original whole-run aggregate rather than leak its hidden count. A separately requested visible-case projection may report only its own currently permitted population and must be labelled partial, without revealing hidden totals. Preserve non-content job status only under its existing safe authority. Erased derived content is unavailable, not reconstructed. Human/JSON/SDK presentation has the same protected meanings.

## Why and example

A run can answer successfully while a metric cannot be calculated. A comparison can also have missing pairs. Those facts must remain visible instead of collapsing into one success flag or score.

Alice runs 20 cases. Nineteen answers finish and one expected passage cannot be mapped. The summary shows the failed execution and unscorable metric separately; it does not pretend every result came from 20 complete pairs.

The result model is more explicit, but readers can distinguish a retrieval problem, a judge problem and an incomplete experiment. Access changes may make an old full summary unavailable.

<a id="decision-trigger-and-stopping-boundary"></a>

## Apply the accepted contract

Use this contract when the original trigger matches. Do not ask for the same policy decision again. Concrete native methods, DTO names and physical schemas are implementation choices consistent with this contract and the repository conventions. Missing measurements, fixtures or assembled evidence block the affected qualification/support claim, not authorized implementation or isolated tests. A failed test is not permission to weaken an accepted safety boundary.

<a id="open-questions-and-required-evidence"></a>

## Implementation and required evidence

Partial answering/scoring, unscorable mappings, no-claim/abstention, missing pairs, repeated reads without effects, shared-access change, budget stop, uncertain child, source/audience revocation and protected aggregate disclosure.

These are required checks, not tests run or successful production evidence. No application edits, paid calls or production changes follow merely from recording this decision.

## Architectural impact and dependencies

Evaluation coordinator/scorers, Pipeline caller contracts, shared jobs, protected history and comparison presentation. Update preparation/execution/scoring/history sequences together.

Load neighboring decisions only under these conditions:

- [PD-PIPELINES-01 (accepted): Capture fixed inputs and complete execution through its receipt](../../inframeld-pipelines/references/decision-execution-build-receipt-contracts.md). For ordinary execution/capture results.
- [PD-INDEXING-03 (accepted): Keep source passage identity stable when chunking changes](../../inframeld-indexing/references/decision-source-coordinates.md). For canonical passage identity.
- [PD-ACCESS-02 (accepted): Keep durable work and credential lifetime explicit](../../inframeld-access-models/references/decision-admitted-work-authority.md). For admitted background-work authority.

## Historical context and alternatives

The following preserves the earlier problem, context and options. Statements that a choice was open describe that earlier analysis. The approved resolution above now settles it.

<a id="problem-and-example"></a>

### Original problem and example

Historical analysis before this resolution.

Alice compares configurations P1 and P2 over 20 frozen cases. One answer fails, one expected passage has no compatible mapping and Bob loses source access before inspecting the results. The comparison must retain its original population without presenting missing pairs as improvements or leaking protected case counts.

The comparison semantics and honest denominators are selected. Exact captured run inputs, child progress, per-metric outcomes and protected-read representations remain open. An overbroad “success/score” result cannot express a valid execution with an unscorable metric or a partially unavailable paired comparison.

### Original accepted context and evidence

Historical context before this resolution. Unchanged invariants still apply.

Both sides run freshly through ordinary Pipelines with fixed benchmark/evaluator/configuration/corpus inputs. Reference answers and expected passages never enter the tested execution. Execution success differs from metric eligibility. Current access and erasure govern historical results.

Preserve missing pairs, failures, exclusions and original permitted scope. No automatic winner, publication permission or reuse of historical scores follows. Shared-current connection changes retain their exact admission/dispatch rules. Durable progress uses existing jobs rather than a separate evaluation runner.

### Considered alternatives and trade-offs

Historical options, resolved by the approved contract above.

1. **Use explicit per-case/per-metric outcomes with bounded progress.** Record actual execution and scoring outcomes separately, then compute summaries over named populations. This supports honest recovery and denominators, but needs carefully scoped protected projections.
2. **Expose a run summary backed by exact retained child evidence.** Keep the public summary compact while retaining typed detailed evidence behind authorized reads. This is easier for clients, but only works if missing/unscorable reasons and denominators remain explicit rather than hidden.

## Sources and finalization

- [Comparison and protected history](generation-and-review.md).
- [Remaining Evaluation contracts](architecture.md#evaluation-operation-boundaries).
- [Evaluation records](records.md#evaluation).

Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later change to this accepted policy. Qualification evidence must identify its artifacts, environment, failures and limits. This record does not fabricate implementation or a passing test.
