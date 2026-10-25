# PD-KNOWLEDGE-01: Finalize a complete collection selection without losing admitted input

**Status:** PENDING

**Owner:** `inframeld-knowledge`

**Issue kind:** Architecture and consistency contract.

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

Alice admits handbook B2, then loses her response before the collection selection finishes. Bob admits C2 against the earlier R1 selection. His automatic update becomes newest. The system must preserve both accepted document outcomes without silently deciding that Alice’s incomplete workflow selected Bob’s corpus.

Focused document and selection operations are accepted, but their consistency boundary, complete-batch marker and durable publication handoff remain open. Separate transaction-owning services cannot simply call each other inside one transaction. Independent commits without recovery can lose the connection between admitted input and the intended selection.

## Accepted context and evidence

DocumentVersions and CollectionRevisions remain immutable. Partial uploads may retain successfully admitted documents without claiming a complete batch. Replacing bytes alone does not select a new corpus. Complete authorized live-input work supplies publication authority separately from Indexing readiness.

ADR-0075 selects focused operations plus a coordinating application workflow. ADR-0077 keeps builds and answer execution distinct, and ADR-0079 protects Deployment transitions. Existing operation identities, current audiences, current authority and required audit remain authoritative.

## Alternatives and trade-offs

1. **Durable admissions followed by conditional batch finalization.** Save each admitted outcome, then conditionally finalize exact membership and a recoverable handoff. This supports partial outcomes and restarts, but needs explicit parent/child identities and a reviewed conflict rule.
2. **One short final SQL transaction over already durable artifacts.** Stage and verify bytes first, then finalize the complete selection and admission metadata in one caller-owned transaction through suitable lower-level capabilities. This reduces intermediate SQL states but requires bounded work and cannot include storage/model waits.

## Non-binding recommendation

**Proposal only.** Prefer durable per-document outcomes with an explicit complete-selection finalization and durable handoff. Use short atomic SQL updates where needed without nesting complete service transactions. A competing selection should lead to the agreed conflict/review behavior, never an unreviewed merge or retargeted retry.

## Decision trigger and stopping boundary

Before implementing batch completion, collection selection, parent/child recovery or the ingestion-to-automatic-update handoff.

Pause the dependent consistency/handoff design. Ordinary source inspection and accepted standalone version admission need not resolve unrelated release details.

## Architectural impact and dependencies

Knowledge admissions and manifests, collection revision selection, shared operation records, Pipeline preparation and Releases newest-request admission. Update replacement/upload-to-publication sequences and affected record notes together.

Load neighboring decisions only under these conditions:

- [PD-PIPELINES-01: Capture fixed inputs and complete execution through its receipt](../../inframeld-pipelines/references/decision-execution-build-receipt-contracts.md). For exact captured build inputs and preparation handoff.
- [PD-RELEASES-01: Persist Deployment transitions with one shared control check](../../inframeld-releases/references/decision-deployment-state-and-concurrency.md). For atomic newest-request/control state.
- [PD-ACCESS-02: Keep durable work and credential lifetime explicit](../../inframeld-access-models/references/decision-admitted-work-authority.md). If a queued continuation must interpret the initiating credential’s lifetime.

## Open questions and required evidence

- What exactly establishes batch completeness?
- Which facts are committed together and which require a durable continuation?
- Which concurrent selection changes conflict rather than combine?
- How does a retry recover each child without losing accepted input or changing original meaning?
- How do application-owned transactions compose without nested begin calls?

## Sources and finalization

- [Accepted Knowledge boundary](../../../../docs/development/knowledge-lifecycle.md#knowledge-operation-boundaries).
- [Focused operations decision](../../../../docs/adr/ADR-0075-separate-document-lifecycle-from-collection-selection.md).
- [Automatic publication](../../../../docs/development/pipelines-and-releases.md#modes).
- [Service transaction ownership](../../../../docs/adr/ADR-0065-application-services-own-write-transactions.md).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/documentation-maintenance.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
