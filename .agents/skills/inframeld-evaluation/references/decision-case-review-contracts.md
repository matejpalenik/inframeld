# PD-EVALUATION-01: Define exact case generation and review operations

**Status:** PENDING

**Owner:** `inframeld-evaluation`

**Issue kind:** Implementation contract.

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

Alice generates starter questions from Support, accepts case revision C1 and freezes it into benchmark B. Bob edits the wording into C2 while Alice’s acceptance request is in flight. Acceptance must apply to the exact reviewed revision, while B keeps its original membership and current source protection.

Generation, immutable content revisions and explicit review are selected. Their exact operation inputs/results, concurrency preconditions and content-review workflow contracts still need definition. A generic save or spending confirmation must not accidentally accept cases or retarget a frozen benchmark.

## Accepted context and evidence

Generation proposes unreviewed revisions. Edited content is unreviewed. Default regression selection uses accepted revisions, while exploratory inclusion is explicit and labelled. Starter generation requests 20 single-passage cases with bounded shortfalls, not unbounded regeneration.

Preserve distinct generation/review authority, exact source provenance, current audience checks and human-versus-application attribution. Audience administration is not content acceptance. Import does not inherit foreign review authority. ADR-0078 selects focused case work rather than a generic Dataset platform.

## Alternatives and trade-offs

1. **Expose focused revision-conditional operations.** Generate, edit and review through explicit owning operations naming exact revisions and preconditions. This makes authority and stale-review failure clear, but requires several narrow result contracts.
2. **Use a bounded reviewed batch with exact per-case selections.** Allow a meaningful review batch whose members each name exact revisions and actions. This can help the CLI, but must define partial outcomes and cannot become blanket acceptance of unseen edits.

## Non-binding recommendation

**Proposal only.** Prefer focused exact-revision operations first. Add bounded batching only where a concrete workflow benefits. Specify stale review, protected reads and generation shortfalls without changing the already selected review-reset invariants.

## Decision trigger and stopping boundary

Before implementing case generation/review commands, revision preconditions, local acceptance or their public result contracts.

Pause affected operation design. Do not reopen the accepted distinction between generation, review and evaluation.

## Architectural impact and dependencies

Evaluation case services/records, case audience checks, JSONL transfer and CLI review presentation. Update generate/edit/review sequences and exact record/wire notes together.

Load neighboring decisions only under these conditions:

- [PD-EVALUATION-03: Qualify embedded Ragas without hidden calls or false confidence](decision-ragas-integration-and-calibration.md). When implementing generator adapters or calibration-dependent claims.
- [PD-KNOWLEDGE-02: Choose bounded retention without weakening explicit erasure](../../inframeld-knowledge/references/decision-retention-erasure-policy.md). For protected case history and erasure.

## Open questions and required evidence

- Which exact expected revision identifies the reviewed content?
- Which result distinguishes saved drafts, accepted revisions and partial generation?
- Which known-ineligible batch choices reject before effects?
- How are concurrent edits, lost responses and removed source access recovered safely?

## Sources and finalization

- [Generation and review](generation-and-review.md).
- [Evaluation operation split](../../../../docs/adr/ADR-0078-separate-evaluation-case-work-run-coordination-and-scoring.md).
- [Case and benchmark records](records.md#evaluation).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
