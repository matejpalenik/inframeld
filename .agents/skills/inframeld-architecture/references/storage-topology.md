# Durable storage and ownership

Alice restores Support after a host failure. Its database, artifact namespace and vector data must agree. This view explains what each store owns, which paths must survive and which claims still need qualification.

<a id="runtime-deployment-and-durable-storage"></a>

Support runs on one server. Its API admits requests, its worker continues saved work and its stores preserve different kinds of state. This is the accepted runtime design with explicitly proposed storage details, not a production Compose file.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="configure-complete-durable-storage"></a>

<a id="storage"></a>

<a id="4-configure-complete-durable-storage"></a>

## Configure complete durable storage

Local trials and production use the same proposed arrangement: **one SeaweedFS process with master, volume, local filer metadata, and S3 enabled**.

| SeaweedFS role | What must be accounted for |
| --- | --- |
| **Master** | The master’s state and its explicitly configured durable directory. |
| **Volume** | Stored object chunks and their durable directory. |
| **Filer** | Metadata mapping object names and attributes to stored chunks. This metadata is separate from application PostgreSQL. |
| **S3** | The private object API used by authorized backend clients. |

The command proposed for testing is `weed server -filer -s3`, with explicit durable paths, static backend credentials, and unused listeners disabled. It keeps these roles in one container without a separate metadata database or cluster manager.

**This is a recommendation to test, not an already-qualified production Compose file.**

<a id="fix-paths-and-disable-unnecessary-listeners"></a>

### Fix paths and disable unnecessary listeners

The recorded review of SeaweedFS 4.47 identified the following settings to test. They are version-specific evidence, not a claim about every later release:

| Example setting | Purpose |
| --- | --- |
| `-dir=/data/volume` | Explicit volume-data location. |
| `-master.dir=/data/master` | Separate master-state location. |
| `-s3.config=/run/secrets/seaweed-s3.json` | Operator-supplied static S3 credential configuration. |
| `-s3.port.iceberg=0` | Disable the Iceberg listener. |
| `-s3.port.lance=0` | Disable the Lance listener. |
| `-s3.iam=false` | Disable the optional S3 identity/access-management subsystem. |

Also disable WebDAV, SFTP, debug, and telemetry functionality. Set replication, volume-size and volume-count limits, and the free-space threshold for accepting work from the tested disk budget. Include these paths in the backup inventory. The table is **not a complete deployable command**. Recorded reference: [SeaweedFS 4.47 server options](https://github.com/seaweedfs/seaweedfs/blob/4.47/weed/command/server.go).

Configure one embedded `[leveldb2]` filer store in `filer.toml`, with `enabled=true` and `dir=/data/filer`. Disable other stores and persist the **whole `/data` tree**. Never let the process’s default working directory decide where persistent metadata goes.

This embedded metadata store does not require another database service, but it does create data that the backup must include. Recorded references: [filer store configuration](https://github.com/seaweedfs/seaweedfs/blob/4.47/weed/command/scaffold/filer.toml) and [LevelDB2 implementation](https://github.com/seaweedfs/seaweedfs/blob/4.47/weed/filer/leveldb2/leveldb2_store.go).

<a id="do-not-substitute-an-unreviewed-quick-start"></a>

### Do not substitute an unreviewed quick start

`weed mini` also combines the components. However, the recorded 4.47 inspection found that it starts an administration/maintenance-worker subsystem even with `-admin.ui=false`. WebDAV and additional S3 catalog listeners also need attention. It persists `mini.options` and can generate local **server-side encryption (SSE)** key files.

For those reasons, the generic mini quick start is not the secured configuration selected for testing. Do not copy its default ports and command into production or add a second trial arrangement without a need. Recorded reference: [tagged mini startup and persistence](https://github.com/seaweedfs/seaweedfs/blob/4.47/weed/command/mini.go).

<a id="verify-access-control-and-actual-durability"></a>

### Verify access control and actual durability

Only API/worker clients need the S3 interface. Keep master, volume, and raw filer endpoints off the public ingress and separated from untrusted services.

Before release, configure explicit credentials and test that unauthorized requests are rejected. A running S3 endpoint does not prove that authentication is active.

Pin and test the settings that control when writes reach durable storage. Test recovery after interrupted writes too. A successful HTTP upload alone does not prove that the data survives power loss. [Upgrades and recovery](../../../../docs/development/operations/upgrades.md) owns the complete backup inventory and proposed stop, copy, and restore procedure.
