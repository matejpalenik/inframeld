# PD-EVALUATION-01: Define exact case generation and review operations

**Status:** ACCEPTED on 2026-10-29 in [ADR-0113](../../../../docs/adr/ADR-0113-review-exact-case-revisions-and-preserve-generation-shortfalls.md). Implementation and qualification remain separate delivery work.

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

Use focused generate, edit, review and benchmark-freeze operations with explicit expected state. Generation fixes Pipeline/Project, current admitted actor/source/audience scope, exact processed source versions/artifacts/spans, preset/seed, requested count, selected generator connection/model/settings and stable parent/child request identities. Starter generation requests 20 single-passage cases. The initial general bound is 1–100 requested cases per operation, with bounded original units rather than regeneration until the count is reached.

Save each successful proposal as a stable case identity plus an immutable unreviewed content revision and exact generation/scenario provenance. The result separates requested, proposed, rejected/failed, uncertain and unattempted units. Seventeen valid proposals out of twenty remain seventeen drafts plus three unfinished outcomes. No spending confirmation or job completion accepts content. Source processing is reused; starter generation performs no new parsing, embeddings or relationship-graph construction.

Editing names the exact case, expected current content revision and audience revision. Check current edit/source authority and atomically append a new immutable unreviewed revision, update the case's current revision, audit and safe original outcome. A stale edit conflicts. The old revision and an already frozen benchmark keep their identity, subject to current access and erasure.

Accept, reject and defer name the exact reviewed content revision, expected current revision/review state and current audience/source binding. Recheck the separate review action at commit. Accept/reject against an intervening content or audience change conflicts rather than accepting unseen content. Defer remains unreviewed. Record actual reviewer principal and human/application kind, time and bounded reason. Application acceptance is never labelled human-reviewed. Import cannot transfer a foreign accepted label into local authority.

Focused one-case mutations are the initial primitive. A CLI review batch is a bounded composition of stable child operations, at most 100, with exact per-case revision/action selections. Reject known ineligible choices before mutations, then preserve independently committed child outcomes if authority or state changes later. No all-case transaction or blanket acceptance of future edits. Replays recover each original child under current disclosure rather than duplicate review.

Benchmark freezing atomically saves one immutable ordered case/revision selection and its recorded review state. Default regression includes current accepted revisions of active cases only. Explicit exploratory inclusion of unreviewed revisions is labelled and frozen. Subsequent edits/reviews do not retarget the benchmark. Case audience administration remains separate and adds no content acceptance. Current sources/audiences protect generation, all reads and erasure.

## Why and example

Generating a question, editing it and approving it are different actions. Approval should apply only to what someone actually reviewed.

Alice reviews case C1 while Bob edits it into C2. Alice's stale approval conflicts. C2 is unreviewed, while an older benchmark still refers to its original exact revision.

Narrow operations and explicit partial outcomes take more bookkeeping, but prevent unseen edits and failed generation from looking like accepted test coverage.

<a id="decision-trigger-and-stopping-boundary"></a>

## Apply the accepted contract

Use this contract when the original trigger matches. Do not ask for the same policy decision again. Concrete native methods, DTO names and physical schemas are implementation choices consistent with this contract and the repository conventions. Missing measurements, fixtures or assembled evidence block the affected qualification/support claim, not authorized implementation or isolated tests. A failed test is not permission to weaken an accepted safety boundary.

<a id="open-questions-and-required-evidence"></a>

## Implementation and required evidence

Concurrent edit/review and audience changes; partial generation; case/source erasure; lost responses; application versus human reviewer; exact benchmark membership and safe per-child continuation.

These are required checks, not tests run or successful production evidence. No application edits, paid calls or production changes follow merely from recording this decision.

## Architectural impact and dependencies

Evaluation case services/records, case audience checks, JSONL transfer and CLI review presentation. Update generate/edit/review sequences and exact record/wire notes together.

Load neighboring decisions only under these conditions:

- [PD-EVALUATION-03 (accepted): Qualify embedded Ragas without hidden calls or false confidence](decision-ragas-integration-and-calibration.md). When implementing generator adapters or calibration-dependent claims.
- [PD-KNOWLEDGE-02 (accepted): Choose bounded retention without weakening explicit erasure](../../inframeld-knowledge/references/decision-retention-erasure-policy.md). For protected case history and erasure.

## Historical context and alternatives

The following preserves the earlier problem, context and options. Statements that a choice was open describe that earlier analysis. The approved resolution above now settles it.

<a id="problem-and-example"></a>

### Original problem and example

Historical analysis before this resolution.

Alice generates starter questions from Support, accepts case revision C1 and freezes it into benchmark B. Bob edits the wording into C2 while Alice’s acceptance request is in flight. Acceptance must apply to the exact reviewed revision, while B keeps its original membership and current source protection.

Generation, immutable content revisions and explicit review are selected. Their exact operation inputs/results, concurrency preconditions and content-review workflow contracts still need definition. A generic save or spending confirmation must not accidentally accept cases or retarget a frozen benchmark.

### Original accepted context and evidence

Historical context before this resolution. Unchanged invariants still apply.

Generation proposes unreviewed revisions. Edited content is unreviewed. Default regression selection uses accepted revisions, while exploratory inclusion is explicit and labelled. Starter generation requests 20 single-passage cases with bounded shortfalls, not unbounded regeneration.

Preserve distinct generation/review authority, exact source provenance, current audience checks and human-versus-application attribution. Audience administration is not content acceptance. Import does not inherit foreign review authority. ADR-0078 selects focused case work rather than a generic Dataset platform.

### Considered alternatives and trade-offs

Historical options, resolved by the approved contract above.

1. **Expose focused revision-conditional operations.** Generate, edit and review through explicit owning operations naming exact revisions and preconditions. This makes authority and stale-review failure clear, but requires several narrow result contracts.
2. **Use a bounded reviewed batch with exact per-case selections.** Allow a meaningful review batch whose members each name exact revisions and actions. This can help the CLI, but must define partial outcomes and cannot become blanket acceptance of unseen edits.

## Sources and finalization

- [Generation and review](generation-and-review.md).
- [Evaluation operation split](../../../../docs/adr/ADR-0078-separate-evaluation-case-work-run-coordination-and-scoring.md).
- [Case and benchmark records](records.md#evaluation).

Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later change to this accepted policy. Qualification evidence must identify its artifacts, environment, failures and limits. This record does not fabricate implementation or a passing test.
