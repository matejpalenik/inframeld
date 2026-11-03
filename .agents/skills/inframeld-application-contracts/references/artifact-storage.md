# Publish immutable artifacts through the storage boundary

<a id="publish-immutable-artifacts-through-the-storage-boundary"></a>

Alice’s upload reaches object storage before its database reference is published. The application verifies complete bytes first. A failed or late upload may leave an owned orphan, but cannot silently become an admitted Document.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

## Implemented allocation and obligation persistence

The internal [allocation service](../../../../apps/backend/src/inframeld_backend/shared/application/services/artifact_allocation_service.py) reserves an immutable attempt, local and remote byte allowances, the original abandoned-staging obligation, one cleanup queue slot and required audit in one transaction. [Migration 0015](../../../../apps/backend/migrations/versions/0015_artifact_allocation.py) adds their records above the delivered deletion-status and Project-metadata migrations. It preserves product job identity and replay while allowing a separately bound cleanup execution.

Equivalent allocation retries recover the original reservation, obligation, cleanup JobId and fixed deadlines. A changed obligation identity, target, origin or request meaning cannot reuse that allocation. A business OperationId and its original RequestId are attribution, not a cleanup execution identity or an incoming credential. Staging that precedes business admission instead retains its exact server-owned attempt and original RequestId.

Allocation applies the accepted byte and projected free-space limits to a supplied trusted [capacity observation](../../../../apps/backend/src/inframeld_backend/shared/application/dtos/artifact_capacity_dto.py). This component does not measure the host or configure storage. Dormant cleanup reserves queue capacity before private effects, but consumes neither an active slot nor an attempt before the original transfer deadline. The [job workflow](jobs-and-recovery.md#implemented-artifact-cleanup-binding) describes its current-fence and original-obligation checks.

This allocation foundation does not itself perform object I/O or settle reservations. Tests that supply trusted capacity or stored cleanup facts qualify those internal contracts only. A terminal cleanup job cannot establish physical deletion or release its retained obligation and bytes.

## Internal S3 adapter and verification

The internal [storage contract](../../../../apps/backend/src/inframeld_backend/shared/application/protocols/artifact_store.py) separates object I/O from admission and publication. Its [S3 adapter](../../../../apps/backend/src/inframeld_backend/shared/infrastructure/resources/s3_artifact_store.py) conditionally creates the original attempt's immutable object, streams reads, inspects exact objects, lists one bounded scope and deletes an exact object. The [verification service](../../../../apps/backend/src/inframeld_backend/shared/application/services/artifact_verification_service.py) compares the complete readback's byte length and SHA-256 with the original trusted expectation. Object metadata and `ETag` alone cannot establish that match.

Before `PUT`, the caller must durably record unresolved-write evidence. For Alice's upload, a conflict or lost write acknowledgment retains the original attempt and key. Read back that same object before deciding whether its bytes match. Neither a client timeout nor drained client calls prove that a server-side write can no longer finish. Successful verification establishes byte integrity, not current publication authority or reservation settlement.

This supporting component excludes local staging ports and resources. Production composition with capacity allocation, conditional publication and cleanup, crash settlement, server late-write exclusion and positive physical-retirement proof remain unfinished in #40. The ordinary worker still registers no handlers. These are implementation and automated-qualification gaps, not deferred human acceptance. The internal adapter exposes no public upload API, SDK or command.

The [private SeaweedFS tests](../../../../docs/development/guides/testing.md#private-seaweedfs-artifact-checks) describe the native cases and their limits. Bounded live-instance S3 protocol and complete readback coverage has been exercised through the private Podman fixture. Docker and other platform checks remain required. The production projected free-space policy remains 20%. The development test budget in that runbook does not change production admission policy.

<a id="a-delayed-seaweedfs-upload-has-the-same-problem"></a>

### A delayed SeaweedFS upload has the same problem

A SeaweedFS `PUT` uploads a source, artifact, or retry payload. If it is still in flight, it may finish after an earlier deletion and recreate bytes even though PostgreSQL will never publish their reference.

Give each upload attempt an immutable key that identifies its ownership scope and physical attempt. Keep evidence of uploads whose outcome is still unknown.

Mark physical deletion complete only after earlier writes have finished or cannot finish, and final cleanup has been checked. **PostgreSQL can block access and publication, but cannot cancel a request already running in the object store.**

<a id="publish-immutable-artifacts-safely"></a>

<a id="artifacts"></a>

<a id="3-publish-immutable-artifacts-safely"></a>

## Publish immutable artifacts safely

**SeaweedFS is the supported v1 S3 implementation.** It stores objects on the host's disks. API and worker code reach those objects through Inframeld's `ArtifactStore` interface and its S3 adapter.

`ArtifactStore` defines the operations the application needs. Its adapter translates them into storage calls. Domain objects must not expose buckets, object keys, or storage SDK types. That separation keeps Knowledge and Releases independent of the storage product if a cloud adapter is added later.

Give API and worker credentials only the storage access they need, rather than an administrative root key. Browsers and project integrations use Inframeld's authorized upload and download routes. Direct bucket credentials would let them bypass document-group permissions.

S3 identity integration, public bucket access, user-managed bucket policies, and a separate object-storage administration product are not required.

<a id="implement-only-the-required-storage-operations"></a>

### Implement only the required storage operations

| Requirement | Expected behavior |
| --- | --- |
| **Streaming** | Stream immutable source, processing, and manifest bytes. Generate opaque keys on the server, never from uploaded paths. An opaque key has no caller-controlled filesystem meaning. |
| **Operation subset** | Support `PutObject`, `GetObject`, `HeadObject`, bounded `ListObjectsV2`, and `DeleteObject`, with verified size/checksum behavior. These write, read, inspect, list, and delete objects. |
| **Multipart uploads** | Enable multipart operations only when the selected artifact bounds require them. If enabled, clean up incomplete uploads. |
| **Publication** | Publish the PostgreSQL artifact reference only after the object upload is complete and verified. A failed upload cannot become a successful document or materialization reference. A materialization is a prepared searchable index. |
| **Checksums** | Never assume an object `ETag` is always a content checksum. Verify the selected server/SDK behavior. |
| **Compatibility** | Pin and test endpoint addressing, TLS/customer certificate-authority trust, request signing, and checksums. “S3-compatible” does not mean every AWS extension exists. |
| **Retention** | Storage lifecycle rules must not expire objects referenced by retained current, candidate, or previous releases. Application retention/deletion owns those decisions. |

<a id="upload-immutable-objects-then-publish-their-references"></a>

### Upload immutable objects, then publish their references

Give each upload attempt a new object key and keep its bytes unchanged. This prevents two attempts from overwriting one another. Verify the completed upload before a PostgreSQL transaction publishes its reference, and publish only if that attempt is still allowed to do so.

```text
Upload under a new attempt-specific object key
    -> Verify the completed object
        -> Conditionally publish its reference in PostgreSQL
```

A successful upload followed by an application crash may leave an unreferenced object for bounded cleanup. Retrying must not replace an already-published artifact with different bytes.

An upload can finish after the application has already tried to clean it up. The result is an **orphan**, an object with no live application reference. While an earlier upload is unresolved, one “not found” check cannot prove final deletion. Keep the attempt record and the **tombstone**, the permanent record that its identity is retired. Test how the storage adapter establishes that old uploads can no longer finish.

These rules govern how the adapter uploads and publishes objects. They do not require building a storage engine. Object versioning or a replica on the same host does not replace an off-host backup.
