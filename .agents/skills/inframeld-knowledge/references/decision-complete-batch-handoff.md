# PD-KNOWLEDGE-01: Finalize a complete collection selection without losing admitted input

**Status:** ACCEPTED

**Approval date:** 2026-10-29

**Owner:** `inframeld-knowledge`

**Issue kind:** Architecture and consistency contract.

The developer explicitly approved this proposal and its detailed batch-3 contract on 2026-10-29, then requested repository and GitHub recording. [ADR-0106](../../../../docs/adr/ADR-0106-finalize-complete-batches-with-durable-conditional-handoff.md) records the decision. Acceptance selects logical behavior, not implemented code or passing qualification.

## Contents

- [Problem and example](#problem-and-example)
- [Accepted context and evidence](#accepted-context-and-evidence)
- [Alternatives and trade-offs](#alternatives-and-trade-offs)
- [Approved resolution](#approved-resolution)
- [Decision trigger and stopping boundary](#decision-trigger-and-stopping-boundary)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Implementation and required evidence](#implementation-and-required-evidence)
- [Sources and finalization](#sources-and-finalization)

## Problem and example

Alice admits handbook B2, then loses her response before the collection selection finishes. Bob admits C2 against the earlier R1 selection. His automatic update becomes newest. The system must preserve both accepted document outcomes without silently deciding that Alice’s incomplete workflow selected Bob’s corpus.

Focused document and selection operations are accepted, but their consistency boundary, complete-batch marker and durable publication handoff were the original gap. The approved resolution below selects the contract. Separate transaction-owning services cannot simply call each other inside one transaction. Independent commits without recovery can lose the connection between admitted input and the intended selection.

## Accepted context and evidence

DocumentVersions and CollectionRevisions remain immutable. Partial uploads may retain successfully admitted documents without claiming a complete batch. Replacing bytes alone does not select a new corpus. Complete authorized live-input work supplies publication authority separately from Indexing readiness.

ADR-0075 selects focused operations plus a coordinating application workflow. ADR-0077 keeps builds and answer execution distinct, and ADR-0079 protects Deployment transitions. Existing operation identities, current audiences, current authority and required audit remain authoritative.

## Alternatives and trade-offs

1. **Durable admissions followed by conditional batch finalization.** Save each admitted outcome, then conditionally finalize exact membership and a recoverable handoff. This supports partial outcomes and restarts, but needs explicit parent/child identities and a reviewed conflict rule.
2. **One short final SQL transaction over already durable artifacts.** Stage and verify bytes first, then finalize the complete selection and admission metadata in one caller-owned transaction through suitable lower-level capabilities. This reduces intermediate SQL states but requires bounded work and cannot include storage/model waits.

<a id="non-binding-recommendation"></a>

## Approved resolution

Use durable per-document admission followed by explicit, conditional finalization of the fixed batch. Save a parent operation with its original principal and Project, immutable batch manifest, stable child request identities, exact intended selection and expected base CollectionRevision/control revision. The manifest fixes the members and their input meanings before finalization. Later files form another batch. Audiences and other effective inputs are explicit, not re-read from changed upload defaults on retry.

Each child admits one verified complete durable source through the existing focused operation. Save its original document/version outcome and checkpoint. Recover that child on retry. The same request identity with different bytes, target or meaning conflicts. Confirmed admissions survive a later sibling failure. An uncertain child admission is reconciled before another is attempted.

The batch is admission-complete only when every original manifest member has a confirmed successful admission and the exact intended complete selection has been finalized. Parsing, embedding and readiness are later outcomes. Successfully admitting two of three files cannot mark a three-file batch complete, select a smaller corpus or authorize publication. Safe continuation may finish the missing original child. Deliberately dropping a failed file or combining another person's selection requires a separately reviewed operation with a new meaning.

Prepare large immutable membership inventories and their verified manifest evidence in bounded pages. Finalization then uses a short application-owned SQL transaction to recheck current authority, source/lifecycle constraints and expected selection revision. Commit the new exact CollectionRevision and selection change, complete-batch marker, original safe outcome, required audit and durable downstream continuation together. The control-state change points to the prepared inventory, rather than doing unbounded artifact/network work inside that transaction. Coordinate source invalidation and selection through the applicable current-state checks.

The durable continuation uses existing job/checkpoint and idempotency facilities, not a new event bus. If a new child job is needed, reserve its finite queue capacity atomically with that admission. If the required atomic finalization/handoff cannot commit, report the unfinished finalization and retain confirmed child admissions for recovery. Do not return a complete batch with a lost handoff.

If Bob changes the selected collection revision first, Alice's finalization conflicts. Keep her accepted versions and original operation visible under current authority. Replaying it does not automatically merge Bob's changes, switch its base revision or produce a different corpus. A new reviewed selection may deliberately combine both sets of changes. A lost finalization response instead recovers the already committed original result.

The coordinating application operation owns finalization's transaction and uses suitable lower-level capabilities. It does not open a transaction around calls to independently transaction-owning complete services. Byte storage, parsing, Chroma and provider waits stay outside SQL transactions.

Collection completion does not itself claim a build or publication succeeded. Downstream work captures exact inputs and uses ordinary current authority. Any live-input intent names explicit Deployment targets and retains the selected configuration/input meaning. Each target has its own admission and outcome through the ordinary release operation. There is no all-Deployment transaction or publication permission inherited from upload. PD-PIPELINES-01 and PD-RELEASES-01 retain their own receipt/control contracts, including newest-authorized-request ordering.

## Alice and Bob example

R1 contains A1, B1 and C1. Alice's fixed batch proposes B2, with intended R2={A1,B2,C1}. B2 is accepted, but her connection drops. Bob separately selects {A1,B1,C2}. Alice reconnects: she finds her existing B2, but her expected-R1 finalization conflicts with Bob's newer selection. Neither person's choice is silently overwritten. Alice can review a new selection {A1,B2,C2} without uploading B2 again.

## Decision trigger and stopping boundary

Apply this accepted contract when the original trigger matches. Concrete method names and physical schemas remain ordinary implementation choices under the repository conventions. Do not reopen the approved policy. Separately pending neighboring choices retain their own triggers. Qualification gaps limit release claims, not authorized evidence gathering.

## Architectural impact and dependencies

Knowledge admissions and manifests, collection revision selection, shared operation records, Pipeline preparation and Releases newest-request admission. Update replacement/upload-to-publication sequences and affected record notes together.

Load neighboring decisions only under these conditions:

- [PD-PIPELINES-01: Capture fixed inputs and complete execution through its receipt](../../inframeld-pipelines/references/decision-execution-build-receipt-contracts.md). For exact captured build inputs and preparation handoff.
- [PD-RELEASES-01: Persist Deployment transitions with one shared control check](../../inframeld-releases/references/decision-deployment-state-and-concurrency.md). For atomic newest-request/control state.
- [PD-ACCESS-02 (accepted): Keep durable work and credential lifetime explicit](../../inframeld-access-models/references/decision-admitted-work-authority.md). If a queued continuation must interpret the initiating credential’s lifetime.

<a id="open-questions-and-required-evidence"></a>

## Implementation and required evidence

These are required cases and evidence, not passing tests.

Lost child/finalization acknowledgments, changed retry payload, partial batch, authority loss and source erasure, competing selections, restart between selection and downstream work, queue-full finalization, large manifests and per-Deployment handoff outcomes. Demonstrate no duplicate child admission or publication and no nested complete-service transactions.

## Sources and finalization

- [Accepted Knowledge boundary](architecture.md#knowledge-operation-boundaries).
- [Focused operations decision](../../../../docs/adr/ADR-0075-separate-document-lifecycle-from-collection-selection.md).
- [Automatic publication](../../inframeld-releases/references/publication-and-automatic-updates.md#modes).
- [Service transaction ownership](../../../../docs/adr/ADR-0065-application-services-own-write-transactions.md).

Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later policy change. This documentation approval does not authorize application edits, a paid qualification call or claims of successful runtime qualification.
