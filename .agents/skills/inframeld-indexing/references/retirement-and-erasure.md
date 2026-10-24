# Retire numerical data without restoring access

Alice erases B1 while a delayed worker still has its old vector payload. Deleting visible records once is not enough. A late write may recreate bytes, so application authority must permanently reject the retired physical identity before cleanup.

## Pins, retirement and tombstones

A pin records that admitted or retained work needs an artifact. Ordinary expiry respects current/candidate/previous versions and active operation pins. Erasure can invalidate those dependencies. Pins and ordinary retirement share the SQL retention gate so one side cannot silently delete data the other just retained.

1. Block affected access and publication under the owning deletion protocol.
2. Permanently tombstone the retired physical identities before deleting their records. A tombstone says that these identities must never regain authority.
3. Perform reference-aware cleanup through the supported writer and durable progress protocol.
4. Account for already dispatched writes that can still recreate unreachable bytes.
5. Use the documented completion barrier for exceptional cleanup. One observation of absence does not prove final physical erasure.

Logical revocation and physical cleanup answer different questions. A query must not regain access merely because bytes reappear. A historical ready state must not override missing dependencies or current erasure.

## Failures and operating limits

Ordinary replay of frozen vector payloads does not require a routine Chroma restart. Corruption, uncertainty about late writes and unresolved cleanup can require intervention. The guide's exceptional barrier and backend qualification determine that outcome. Do not invent a restart policy or claim cancellation of a remote request from a SQL lease.

An unusable candidate is not proof that another independent serving generation is unhealthy. Recheck required dependencies during an operation at the selected boundaries. Ordinary expiry preserves references, while explicit erasure can invalidate retained releases and evaluation evidence.

## Status and sources

These are accepted numerical lifecycle boundaries. The guide includes calculations, proposed workload/resource allocations, stopping rules and tests still needed. They are not certified capacity, recovery time or proof of final erasure. Use measured evidence before making numerical guarantees.

- [Retirement protocol](../../../../docs/development/indexing.md#retirement), [Indexing qualification](../../../../docs/development/indexing.md), [retention/deletion](../../../../docs/development/retention-and-deletion.md), [jobs](../../../../docs/development/jobs-and-idempotency.md) and [Indexing records](../../../../docs/development/data-model.md#indexing).
- [Maintainer checks](../../../../docs/development/indexing.md#maintainer-checks) cover delayed writes, current health, candidate retries, pins and cleanup. Source admission and release authority stay with their own domains.
