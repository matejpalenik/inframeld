# Publish immutable artifacts through the storage boundary

<a id="publish-immutable-artifacts-through-the-storage-boundary"></a>

Alice’s upload reaches object storage before its database reference is published. The application verifies complete bytes first. A failed or late upload may leave an owned orphan, but cannot silently become an admitted Document.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

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
