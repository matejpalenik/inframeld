# PD-INDEXING-04: Qualify frozen storage retries and final erasure barriers

**Status:** ACCEPTED on 2026-10-29 in [ADR-0119](../../../../docs/adr/ADR-0119-bound-frozen-storage-retries-and-prove-exceptional-erasure-completion.md). Implementation and qualification remain separate delivery work.

**Owner:** `inframeld-indexing`

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

Keep immutable generation IDs, exact explicit record IDs and frozen canonical finite float32 payload bytes before vector dispatch. Retrying storage reuses those exact bytes and recorded placement. Verify actual numerical/content readback against the trusted frozen expectation and qualified engine representation. A conflicting existing ID/payload is an integrity failure, not permission to overwrite or regenerate. This does not authorize another possibly billed embedding call.

Initial saved dispatch batches are at most 128 records or 8 MiB, with a 30-second request deadline. Allow at most three submissions per saved batch across the whole operation, with 1-second then 5-second retry delays. These counters do not reset on worker/application attempt, resume or restart and do not multiply the existing three-application-attempt bound. At most two unresolved storage requests per generation and eight installation-wide may exist; reaching either bound stops additional dispatch until reconciled. Reserve frozen spool capacity before effects:256 MiB per job and 2 GiB installation-wide. Partial success remains unready. Duplicate/partial-add and readback semantics require pinned-backend qualification.

Retirement first shares the ordinary retention gate, disables reuse and permanently tombstones the physical identity. Delete exact IDs from its manifest, not broad mutable scope. New writes/retries and delayed publication must obey the tombstone, while acknowledging that an already accepted remote request may still complete. Logical denial is immediate under its existing boundary; physical cleanup is pending until completion is proved.

Select controlled stop/drain as the initial exceptional barrier when delayed writes cannot otherwise be excluded. Block affected access and new retries, identify every possible old writer, stop/drain those clients, cleanly stop the relevant stores, restart privately, and establish that previously accepted background/replay-log work has finished or is excluded. Then delete the exact retired IDs/artifacts through the singleton authorized writer and verify absence. A client restart, healthy server restart or one empty read is insufficient. Apply the procedure to both Chroma and delayed SeaweedFS PUTs and retain original cleanup identities/observations.

Pinned-version hostile-timing tests must establish the actual barrier, including duplicate partial requests, accepted-but-late work, server restart/replay and artifact completion. If they cannot, do not select another engine, weaken erasure or invent remote cancellation. Keep cleanup physically pending and the capability unqualified. This is a settled fail-closed policy and qualification task, not a request for another human choice before writing tests.

Remove frozen spool payloads within 24 hours after replay becomes permanently unnecessary and no pending obligation needs them. Do not expire required payloads merely by age. Lost/corrupt frozen bytes make that original replay ineligible; preserve attribution and require explicit retirement or a genuinely new admitted numerical generation, never paid re-embedding under old IDs. Unknown paid-call holds and non-content tombstones retain their independent safety lifetime.

## Why and example

A timed-out storage request may still finish later. Reusing already known bytes is different from buying another embedding, and deleting data is not complete while old writes could recreate it.

Alice deletes retired generation G1 after a retry succeeded. Bob's original delayed request could still arrive. G1 remains blocked immediately, but final erasure is reported only after the proven completion barrier excludes that old write.

Exceptional cleanup may briefly stop affected stores. If the backend cannot prove completion, the honest outcome is pending physical cleanup, not a false erasure guarantee.

<a id="decision-trigger-and-stopping-boundary"></a>

## Apply the accepted contract

Use this contract when the original trigger matches. Do not ask for the same policy decision again. Concrete native methods, DTO names and physical schemas are implementation choices consistent with this contract and the repository conventions. Missing measurements, fixtures or assembled evidence block the affected qualification/support claim, not authorized implementation or isolated tests. A failed test is not permission to weaken an accepted safety boundary.

<a id="open-questions-and-required-evidence"></a>

## Implementation and required evidence

Pinned Chroma duplicate/add/readback behavior, partial/lost acknowledgments, request counters across restart, spool loss, delayed writes after retirement and qualified Chroma/SeaweedFS drain/replay completion.

These are required checks, not tests run or successful production evidence. No application edits, paid calls or production changes follow merely from recording this decision.

## Architectural impact and dependencies

Indexing writer/reconciliation, Knowledge artifact cleanup, shared job attempts, erasure status and restore restrictions. Update late-write/deletion sequences with the proven barrier, not a fictitious remote cancellation.

Load neighboring decisions only under these conditions:

- [PD-KNOWLEDGE-02 (accepted): Choose bounded retention without weakening explicit erasure](../../inframeld-knowledge/references/decision-retention-erasure-policy.md). For shared reference/erasure policy.
- [PD-ACCESS-02 (accepted): Keep durable work and credential lifetime explicit](../../inframeld-access-models/references/decision-admitted-work-authority.md). Only when a recovery continuation must interpret credential lifetime.

## Historical context and alternatives

The following preserves the earlier problem, context and options. Statements that a choice was open describe that earlier analysis. The approved resolution above now settles it.

<a id="problem-and-example"></a>

### Original problem and example

Historical analysis before this resolution.

A vector add times out. Its frozen retry succeeds, the generation is retired and deleted, then the original add completes late and recreates bytes. Access remains blocked by the tombstone, but the operator cannot honestly claim final physical erasure. A delayed artifact PUT has the same problem.

The accepted protocol is conditional on concrete backend behavior and a completion barrier proving old writes cannot still arrive. Pinned Chroma duplicate/add/readback/restart behavior and a qualified SeaweedFS completion procedure are not established by SQL fences or an empty read.

### Original accepted context and evidence

Historical context before this resolution. Unchanged invariants still apply.

Preserve captured exact IDs and float32 payload bytes, full verification, immutable numerical generations, singleton vector writing and permanent retired identities. A storage retry differs from redispatching an uncertain paid embedding request. Logical denial precedes physical cleanup.

A completion barrier is evidence that earlier writes can no longer recreate the deleted content. It may require draining the actual writer/runtime. A timeout or expired SQL lease is not that evidence. Tests may expose an unsupported assumption, but cannot silently change the selected engine or guarantee.

### Considered alternatives and trade-offs

Historical options, resolved by the approved contract above.

1. **Use a qualified backend completion/ordering boundary.** Prove through the supported backend protocol that all prior writes are completed or excluded before final deletion. This permits ordinary operation, but depends on actual pinned-version guarantees and hostile timing tests.
2. **Stop and drain the responsible writer before completion.** Use a controlled runtime boundary and verify storage after draining all possible earlier writes. This is operationally simpler to reason about, but can interrupt work and still requires proof that outstanding backend work is finished.

## Sources and finalization

- [Frozen retries and retirement](profiles-and-preparation.md).
- [Physical deletion obligations](../../inframeld-knowledge/references/deletion-and-retention.md).
- [Frozen payload decision](../../../../docs/adr/ADR-0011-retry-frozen-vector-identities-and-payloads.md).
- [Logical blocking before cleanup](../../../../docs/adr/ADR-0039-block-access-before-resumable-physical-deletion.md).

Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later change to this accepted policy. Qualification evidence must identify its artifacts, environment, failures and limits. This record does not fabricate implementation or a passing test.
