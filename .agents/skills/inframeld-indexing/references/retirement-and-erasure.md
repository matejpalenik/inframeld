# Retire numerical data without restoring access

<a id="retire-numerical-data-without-restoring-access"></a>

Alice erases B1 while a delayed worker still has its old vector payload. Deleting visible records once is not enough. A late write may recreate bytes, so application authority must permanently reject the retired physical identity before cleanup.

## Apply accepted PD-INDEXING-04

Accepted [PD-INDEXING-04](decision-storage-retries-and-erasure.md#approved-resolution) selects this workflow's detailed contract. A timed-out storage request may still finish later. Reusing already known bytes is different from buying another embedding, and deleting data is not complete while old writes could recreate it. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## Apply accepted PD-INDEXING-02

Accepted [PD-INDEXING-02](decision-health-observation.md#approved-resolution) selects this workflow's detailed contract. An index can lose a record without returning an error. Periodic checks can discover that omission, but a ready label or unchanged counter cannot discover it by itself. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## Prepared-binding lifetime

Accepted [PD-INDEXING-01](decision-capability-binding-contracts.md#approved-resolution) uses the existing scoped materialization identity. An admitted operation owns its pin, attempt, deadline and fence. Exact selected usable dependencies and the pin are resolved together through the shared SQL retention gate. Active/retained references block ordinary retirement. A retained snapshot's metadata alone does not retain all historical vectors. Missing dependencies do not authorize automatic reconstruction.

Release an operation pin when use finishes. Lease expiry alone cannot prove that reads or outbound content stopped. Retain the pin or stop and drain the old runtime unless the enforced deadline stops further use and rejects late results. Explicit erasure/revocation retains precedence. Accepted PD-INDEXING-02/04 select current-health observation and physical-completion policy. Passing backend evidence remains required.

<a id="pins-retirement-and-tombstones"></a>

## Pins, retirement and tombstones

A pin records that admitted or retained work needs an artifact. Ordinary expiry respects current/candidate/previous versions and active operation pins. Erasure can invalidate those dependencies. Pins and ordinary retirement share the SQL retention gate so one side cannot silently delete data the other just retained.

1. Block affected access and publication under the owning deletion protocol.
2. Permanently tombstone the retired physical identities before deleting their records. A tombstone says that these identities must never regain authority.
3. Perform reference-aware cleanup through the supported writer and durable progress protocol.
4. Account for already dispatched writes that can still recreate unreachable bytes.
5. Use the documented completion barrier for exceptional cleanup. One observation of absence does not prove final physical erasure.

Logical revocation and physical cleanup answer different questions. A query must not regain access merely because bytes reappear. A historical ready state must not override missing dependencies or current erasure.

<a id="failures-and-operating-limits"></a>

## Failures and operating limits

Ordinary replay of frozen vector payloads does not require a routine Chroma restart. Corruption, uncertainty about late writes and unresolved cleanup can require intervention. The guide's exceptional barrier and backend qualification determine that outcome. Do not invent a restart policy or claim cancellation of a remote request from a SQL lease.

An unusable candidate is not proof that another independent serving generation is unhealthy. Recheck required dependencies during an operation at the selected boundaries. Ordinary expiry preserves references, while explicit erasure can invalidate retained releases and evaluation evidence.

<a id="retire-data-without-restoring-access"></a>

<a id="retirement"></a>

<a id="5-retire-data-without-restoring-access"></a>

## Retire data without restoring access

A query must claim the data it needs before cleanup can remove it. Resolve the target and register its pin in one short PostgreSQL transaction. Cleanup uses the same lock or conditional revision check. This shared check, called the **retention gate**, prevents a query from starting between cleanup's last reference check and deletion.

Once a binding is retiring, a new query cannot pin it. While an existing pin is active, ordinary garbage collection cannot delete it. Count Deployments, candidates, builds, retained rollback versions, and queries. Promoting a new version does not move a query already using the old one.

Release pins when operations finish. For an abandoned operation, expiry is safe only when an enforced deadline stops further reads and outbound content and discards late results.

If the system cannot establish that the old operation has stopped, keep its pin or stop and drain the old query runtime before cleanup. A database timeout alone is insufficient if that operation can still read or send content.

Explicit erasure or revocation overrides ordinary retention and makes affected operations fail safely.

<a id="recheck-dependency-health-during-the-operation"></a>

### Recheck dependency health during the operation

A dependency's **health generation** is a revision number that changes when it becomes unavailable, is found corrupt, or recovers. Writing an unrelated candidate does not change it.

Save that number when the query starts. Compare it after retrieval, before sending content to a provider, and before returning the answer. If it changed, discard the results.

These checks do not make remote calls atomic with SQL, and already-sent text cannot be recalled.

<a id="retire-physical-identities-before-deleting-their-records"></a>

### Retire physical identities before deleting their records

Before ordinary deletion, use the shared retention check to confirm that no references remain. In that same transaction, disable reuse and permanently mark the physical identity as retired. A later build or retry must never make that identity live again.

Delete using explicit record/generation IDs from the manifest. Broad deletion based on mutable scope is forbidden.

Tombstones and job state prevent new application retries. They do **not** cancel an external request already accepted by Chroma.

In the example, promoting P-V2 does not immediately delete GB1. R1 may still be the rollback target, another pipeline may bind M1, or a query may still be using it. After all ordinary references end, GB1 can be tombstoned and its two records removed. GA and GC stay because M2 still needs them.

Removing one user's B access changes that user's filter at the documented authorization boundary. It does not require deleting shared vectors that other authorized users still need.

**Explicit erasure of B is different:** first invalidate all affected serving dependencies, then remove B's owned generations under the deletion protocol rather than preserving them solely for rollback.

<a id="logical-revocation-is-not-proof-of-physical-cleanup"></a>

### Logical revocation is not proof of physical cleanup

A delayed old `add` can finish **after deletion** and recreate an unreachable record. Exact PostgreSQL-selected generation filters keep that tombstoned generation out of every query.

A successful delete followed by one “not found” check is insufficient while an earlier write may still finish. Show the two outcomes separately:

> Logical access revoked / physical cleanup pending.

Keep the attempt records, retry cleanup within its limits, and alert when backlog or disk limits are reached. A successful duplicate insertion does not prove erasure complete and is not a reason to discard the evidence.

For example, b2.2's first request times out, its retry succeeds, and R2 eventually becomes unused. GC retires and deletes GB2. If the original S1 request then finishes, it may insert b2.2 again because the ID is absent.

GB2 remains tombstoned and cannot enter a query filter or new build. User access is not restored, but physical deletion is not yet proven. This cleanup problem does not invalidate the earlier exact-payload retry while GB2 was live.

Delayed artifact or spool uploads need the same honest cleanup status under [Keeping and deleting data deliberately](../../inframeld-knowledge/references/deletion-and-retention.md). A PostgreSQL tombstone does not cancel an in-flight SeaweedFS `PUT` either.

<a id="exceptional-cleanup-needs-a-tested-completion-barrier"></a>

### Exceptional cleanup needs a tested completion barrier

To finish cleanup, establish that all earlier writes have finished or can no longer run. This is called **quiescence**. Tested backend conditions that provide the same guarantee are another option.

On the supported single server, exceptional maintenance may stop the old writer and confirm it exited, then stop and restart Chroma. Establish that Chroma has finished recovering and processing earlier accepted log work. Only then delete the retired IDs, verify their absence, and mark cleanup complete.

A failure test against the pinned server must prove that earlier work cannot run after this cleanup. Restarting only the client cannot prove that. A future cloud adapter needs its own supported equivalent because the local procedure does not control a managed service's queues.

This is exceptional final cleanup, not the response to every lost build response.

Persistent storage failure, identity/hash conflicts, missing published data, corrupt unfinished spool, or cleanup backlog reaching its bound also require intervention. Automatic retries handle routine transient failures, not every possible fault without an operator.

<a id="a-delayed-chroma-insert-can-arrive-after-deletion"></a>

### A delayed Chroma insert can arrive after deletion

An old immutable insert may remain unresolved after its client stops waiting. The following sequence is possible:

```text
An insert is sent; its completion remains unknown
    -> The generation is tombstoned and its records are deleted
    -> A read currently finds no records
    -> The old insert finishes and recreates an unreachable record
```

If an old write recreates a retired record, the record stays inaccessible. PostgreSQL's deletion markers and the generation filters built by the server exclude it from every query. The caller cannot supply a different authoritative filter.

**Tombstoned physical IDs are never reused.** A late insert cannot make the retired generation eligible for a new build or serving request.

A “not found” check proves only that the record was absent at that moment. An unresolved write might still recreate it. Report **“Access revoked. Physical cleanup pending.”** until earlier writes are known to have finished or become unable to finish and final cleanup is verified.

Establishing that old work can no longer arrive after cleanup is called **quiescence**. Keep unresolved-attempt evidence and allow garbage collection, the removal of unneeded data, to retry within its configured limits.

Routine retries of a candidate's saved writes do not need a Chroma restart. Finishing cleanup while an old write remains unresolved may require exceptional maintenance, operator action, or provider help. [Indexing](profiles-and-preparation.md) explains the distinction.

## Status, sources and unresolved scope

<a id="status-and-sources"></a>

These are accepted numerical lifecycle boundaries. The guide includes calculations, proposed workload/resource allocations, stopping rules and tests still needed. They are not certified capacity, recovery time or proof of final erasure. Use measured evidence before making numerical guarantees.

- [Retirement protocol](#retirement), [Indexing qualification](profiles-and-preparation.md), [retention/deletion](../../inframeld-knowledge/references/deletion-and-retention.md), [jobs](../../inframeld-application-contracts/references/jobs-and-recovery.md) and [Indexing records](records.md#indexing).
- [Maintainer checks](profiles-and-preparation.md#maintainer-checks) cover delayed writes, current health, candidate retries, pins and cleanup. Source admission and release authority stay with their own domains.

<a id="decision-and-reference-map"></a>

<a id="decision-map"></a>

<a id="8-decision-and-reference-map"></a>

Automatic re-sharding, multiple writer hosts, distributed management, segment compaction, and a different strategy for very large collections remain deferred. V1 uses one processing and one embedding profile per pipeline. Mixing profiles would need separate embeddings, a defined way to combine scores, readiness checks, and failure rules.

Verify the supported paths with both one and two shards and limited-size inventories. The application interfaces preserve ownership boundaries but do not make future migrations trivial. [Deployment](../../inframeld-architecture/references/runtime-deployment-and-storage.md) describes the separate, untested local-trial proposal. [Recovery](../../../../docs/development/operations/upgrades.md) explains what to do when published data is lost.

| Decision | Rationale |
| --- | --- |
| [ADR-0009](../../../../docs/adr/ADR-0009-keep-application-authority-in-postgresql-and-derived-vectors-in-chroma.md) | Keep application authority in PostgreSQL and derived vectors in Chroma. |
| [ADR-0010](../../../../docs/adr/ADR-0010-save-deterministic-layouts-for-vector-shards.md) | Save deterministic layouts for vector shards. |
| [ADR-0011](../../../../docs/adr/ADR-0011-retry-frozen-vector-identities-and-payloads.md) | Retry frozen vector identities and payloads. |
| [ADR-0040](../../../../docs/adr/ADR-0040-bind-pipeline-versions-to-verified-profile-specific-materializations.md) | Bind pipeline versions to verified profile-specific materializations. |
