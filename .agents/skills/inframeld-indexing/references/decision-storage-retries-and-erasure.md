# PD-INDEXING-04: Qualify frozen storage retries and final erasure barriers

**Status:** PENDING

**Owner:** `inframeld-indexing`

**Issue kind:** Backend implementation contract and qualification.

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

A vector add times out. Its frozen retry succeeds, the generation is retired and deleted, then the original add completes late and recreates bytes. Access remains blocked by the tombstone, but the operator cannot honestly claim final physical erasure. A delayed artifact PUT has the same problem.

The accepted protocol is conditional on concrete backend behavior and a completion barrier proving old writes cannot still arrive. Pinned Chroma duplicate/add/readback/restart behavior and a qualified SeaweedFS completion procedure are not established by SQL fences or an empty read.

## Accepted context and evidence

Preserve captured exact IDs and float32 payload bytes, full verification, immutable numerical generations, singleton vector writing and permanent retired identities. A storage retry differs from redispatching an uncertain paid embedding request. Logical denial precedes physical cleanup.

A completion barrier is evidence that earlier writes can no longer recreate the deleted content. It may require draining the actual writer/runtime. A timeout or expired SQL lease is not that evidence. Tests may expose an unsupported assumption, but cannot silently change the selected engine or guarantee.

## Alternatives and trade-offs

1. **Use a qualified backend completion/ordering boundary.** Prove through the supported backend protocol that all prior writes are completed or excluded before final deletion. This permits ordinary operation, but depends on actual pinned-version guarantees and hostile timing tests.
2. **Stop and drain the responsible writer before completion.** Use a controlled runtime boundary and verify storage after draining all possible earlier writes. This is operationally simpler to reason about, but can interrupt work and still requires proof that outstanding backend work is finished.

## Non-binding recommendation

**Proposal only.** First run the documented pinned-backend failure matrix, then select the smallest barrier supported by evidence for each storage adapter. Keep final erasure pending if neither approach can prove it. Any changed backend or weaker product guarantee requires a separate approved decision.

## Decision trigger and stopping boundary

When implementing frozen-write retry/retirement adapters, selecting artifact completion mechanics or qualifying final-erasure claims.

Approve genuinely unresolved barrier mechanics before depending on them. Missing backend evidence blocks production/final-erasure claims, not qualification tests of the accepted protocol.

## Architectural impact and dependencies

Indexing writer/reconciliation, Knowledge artifact cleanup, shared job attempts, erasure status and restore restrictions. Update late-write/deletion sequences with the proven barrier, not a fictitious remote cancellation.

Load neighboring decisions only under these conditions:

- [PD-KNOWLEDGE-02: Choose bounded retention without weakening explicit erasure](../../inframeld-knowledge/references/decision-retention-erasure-policy.md). For shared reference/erasure policy.
- [PD-ACCESS-02: Keep durable work and credential lifetime explicit](../../inframeld-access-models/references/decision-admitted-work-authority.md). Only when a recovery continuation must interpret credential lifetime.

## Open questions and required evidence

- How does the pinned backend handle partial duplicate inserts and lost acknowledgments?
- Do readbacks preserve the actual expected numerical bytes?
- What proves quiescence across worker and backend restart?
- What barrier covers delayed SeaweedFS PUTs?
- What remains blocked if completion cannot be established?

## Sources and finalization

- [Frozen retries and retirement](profiles-and-preparation.md).
- [Physical deletion obligations](../../inframeld-knowledge/references/deletion-and-retention.md).
- [Frozen payload decision](../../../../docs/adr/ADR-0011-retry-frozen-vector-identities-and-payloads.md).
- [Logical blocking before cleanup](../../../../docs/adr/ADR-0039-block-access-before-resumable-physical-deletion.md).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
