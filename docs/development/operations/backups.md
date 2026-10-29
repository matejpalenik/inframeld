# Backups

<a id="back-up-and-restore-a-complete-installation"></a>

A backup must preserve the database, identity infrastructure, artifacts, vector data and the keys needed to interpret them. The sequence below is the selected single-host operating procedure with chosen qualification targets. It has not been qualified by recording the decision.

<a id="back-up-one-complete-matching-set"></a>

<a id="inventory"></a>

<a id="4-back-up-one-complete-matching-set"></a>

## Accepted backup and recovery objectives

[PD-ARCHITECTURE-02](../../../.agents/skills/inframeld-architecture/references/decision-availability-backup-and-restore.md#approved-resolution) selects the daily coherent cut, 20-minute planned-interruption objective, one-hour verified off-host completion, conditional 25-hour recovery point/four-hour prepared-operator restoration, 98.0% availability objective, seven daily/four weekly completed sets and fail-closed security reconciliation. These are chosen targets, not measured results. The initial workload is the smaller accepted [operating profile](../../../.agents/skills/inframeld-architecture/references/decision-supported-operating-envelope.md#approved-resolution), not the old 25k expansion experiment. Preserve the existing procedures below and qualify them on that profile.

## Back up one complete matching set

Each backup has an **installation manifest**, an inventory explaining what it contains and how to restore it.

Record its cut time, backup ID, image digests, schema and format versions, checksums, storage paths, file ownership and access modes, restore instructions, and security-review coverage. Digests identify exact images, while checksums help check copied files. Keep this inventory with the encrypted backup. Track successful cut and completion times separately.

**Do not mix yesterday’s PostgreSQL with today’s artifact or vector directories.** The following state belongs to one matching set:

| State | Required contents and purpose |
| --- | --- |
| **Complete PostgreSQL cluster** | The **application, Kratos and Hydra databases**, their separate roles/grants, transaction state, write-ahead log (WAL), and configuration outside the data directory. This preserves application records together with Kratos identities/sessions and Hydra's persisted protocol state, grants and official CLI client registration. Application records include jobs/attempts, receipts/idempotency, artifact references, index readiness and Deployment serving pointers. An application-only or application/Kratos-only export is not a complete identity backup. |
| **SeaweedFS namespace and data** | The entire configured filer store, volume directories, and master state, including the private/internal namespace. The proposed paths are `/data/filer`, `/data/volume`, and `/data/master`. Include every directory actually configured, not just those example names. |
| **Chroma persistence** | The complete persistent directory for the selected server version: collection/system state, SQLite/WAL where used, vector index files, and metadata. Include every physical shard and profile referenced by retained releases and unfinished work. A shard is a physical partition of the index. Embeddings alone, collection names, or one SQLite file are not a complete restore. |
| **Protected configuration and recovery secrets** | Compose/configuration files and exact dependency pins, including Kratos, Hydra and the account UI<br>PostgreSQL, Kratos, Hydra and SeaweedFS credentials<br>Kratos schemas, cookie/cipher secrets and configured upstream OIDC client material<br>Hydra system secrets, persisted signing/encryption key material and required client/protocol configuration, wherever the qualified release stores them<br>Canonical API URL, issuer/audience, callback/consent routing and account-UI configuration<br>TLS certificates/keys or a tested reissue path<br>model/provider credentials or restore references<br>application encryption and idempotency-fingerprint keys, including required versions. Back up operator-managed secret files even when Compose mounts them under `/run/secrets`. |
| **Pending work and retention evidence** | Durable job/attempt records, bounded pending payloads required for safe write retries, deletion tombstones, and retention/pin state. Preserve original statuses as evidence. Recovery also needs the separately maintained newer restriction evidence described in [Reconcile newer restrictions before restored data becomes accessible](restore.md#restrictions). |

**WAL** records database changes needed by the database’s recovery process. **OIDC** is the external sign-in protocol. **TLS** protects HTTPS connections. An **idempotency record** identifies a repeated application request, and its fingerprint key supports safe request matching. A **tombstone** records a retired/deleted identity. A **pin** records that retained or active work still needs a resource.

Recovery needs these records as well as the data. An interrupted request remains interrupted until its outcome is established.

<a id="preserve-both-identity-services-then-reconcile-security"></a>

### Preserve both identity services, then reconcile security

Alice's CLI used the installation's registered public client before the host failed. Restoring Kratos accounts but starting Hydra with an empty database or replacement secrets does not restore that installation. A complete backup inventories the actual persisted Hydra state and external recovery material for the pinned release. It must not silently recreate an issuer, client registration or subject mapping to make startup succeed. The public CLI client has no embedded client secret: its registration is required protocol configuration, not a new shared CLI credential.

[Deployment](../../../.agents/skills/inframeld-architecture/references/runtime-deployment-and-storage.md#identity-runtime) owns the runtime arrangement, [Access](../../../.agents/skills/inframeld-access-models/references/human-cli-login.md#human-cli-authentication) owns authentication, and owns the coordinated backup procedure. Record each required store/secret location and version in the protected manifest. Do not assume that copying a database also copies service secrets mounted from the host. Keep backup contents encrypted and operator-restricted. Manifests and logs must not print secret values. TOML configuration export is not a substitute for this backup.

Restoring protocol state does not authorize restored sessions to become usable. Before reopening, follow the newer-restriction checks below and use qualified, documented Ory administration to invalidate restored Kratos browser sessions and Hydra access/refresh grants. Then verify that fresh login uses the preserved issuer/client/identity mapping and current Inframeld admission/permissions. If invalidation or identity consistency cannot be established, keep the affected authenticated surfaces closed. Do not fix a partial restore through automatic account creation, a factory reset or custom token invalidation logic. Qualification must demonstrate this sequence with both identity services and qualify their supported migration/rollback paths as part of the release set. Exact storage inventory, Ory administrative sequence and compatible versions remain implementation/qualification deliverables, not tests performed by this guide.

<a id="postgresql-copy-the-whole-stopped-cluster"></a>

### PostgreSQL: copy the whole stopped cluster

The initial proposal copies the **whole PostgreSQL cluster while it is stopped**. Here “cluster” means the complete database instance, including its databases and shared state. It does not mean a multi-server installation.

Restore using the same PostgreSQL major version and architecture, with a compatible image and configuration. The initial supported setup has no external **tablespaces**, extra locations for database files. If an installation uses them, its inventory must include every location and any external WAL path.

The recorded PostgreSQL 18 references explain why ordinary file copying requires shutdown and why individual table or database files are insufficient. A future logical-dump procedure would need to cover roles and other shared state explicitly. It is not the procedure selected here.

<a id="seaweedfs-preserve-the-map-and-the-bytes-together"></a>

### SeaweedFS: preserve the map and the bytes together

SeaweedFS needs both stored bytes and a map showing where each object's bytes are. The **filer** stores that map: object and directory names, attributes, and ordered storage chunks. Each chunk reference includes a volume ID, file key/cookie, offset, and size, and may refer to a chunk manifest or encryption metadata. These storage chunks are different from the text excerpts Inframeld retrieves.

For example, S3 object `artifacts/source-123` may resolve through the filer bucket namespace to chunks in **volumes 7 and 8**. Keeping only those volume files loses the map from the S3 key to the bytes. Keeping only the filer entry leaves a map to missing bytes.

With [Running the application on one server](../../../.agents/skills/inframeld-architecture/references/runtime-deployment-and-storage.md)’s embedded LevelDB2 configuration, `/data/filer` contains the metadata store, including internal partitions, logs, and manifests. Preserve its **whole tree**, not an export of visible bucket names.

Preserve volume IDs and all files in the configured volume/index directories, including `.dat`, `.idx`, and applicable companion files. Do not rename or reallocate volume IDs during restore. Also retain master metadata, `filer.toml`, `master.toml`, `volume.toml`, and `security.toml` where present, static S3 identity configuration, and configured encryption keys.

Stop SeaweedFS before copying these directories. The proposal copies the complete stopped state together rather than relying on independent background copies of metadata and volumes.

<a id="chroma-use-the-deployed-configuration-as-the-inventory"></a>

### Chroma: use the deployed configuration as the inventory

The recorded inspection of Chroma 1.5.9 found persistent configuration and separate local index state. Build the inventory from the deployed configuration and check it against the selected server version. An old example's default directory may be incomplete.

The [decision map](backup-and-restore.md#decision-map) links the retained storage references. They do not establish that the proposed 100-GiB restore has passed testing.

<a id="create-a-usable-off-host-backup"></a>

<a id="backup"></a>

<a id="5-create-a-usable-off-host-backup"></a>

## Create a usable off-host backup

1. **Check prerequisites.** Record a new backup attempt as in progress. Check free space, off-host access, dependency versions, the latest successful cut, and the [restriction register](restore.md#restrictions). Starting a new attempt must not replace the previous successful-backup marker.
2. **Stop new and running application work.** Close public ingress, including account-UI, Kratos and Hydra protocol routes, and stop accepting jobs. Prevent concurrent private administration/migrations. Allow limited time for running work to finish, then establish that API, worker, parser, account-UI integration, Kratos and Hydra processes have stopped. Resolve or record uncertain attempts using the [Indexing](../../../.agents/skills/inframeld-indexing/references/profiles-and-preparation.md) and [job](../../../.agents/skills/inframeld-application-contracts/references/jobs-and-recovery.md) rules. A client timeout does not prove a storage server stopped writing.
3. **Stop every store cleanly.** Stop Chroma, SeaweedFS, and PostgreSQL, wait for exit, and check the result. This includes internal writers such as object compaction. If shutdown fails, fail the backup attempt and follow the tested crash-recovery procedure before claiming a consistent cut. Never delete volumes or copy beneath a running store.
4. **Copy the complete inventory.** Record the cut and copy into a new private staging directory, preserving ownership and access modes. Check the inventory, checksums, and manifest. Sequential copies represent the same point in time because every store remains stopped. A filesystem snapshot is optional.
5. **Restart and check the live installation.** Start the original stores and matching services. Check login, readiness, and a query against a retained release before reopening. Prevent changes to the staging copy. Service can resume, but **this new backup is not yet safe from host loss**.
6. **Complete the off-host copy.** Encrypt and transfer the frozen set to storage that survives losing this host. Check transfer completion, repository integrity, and manifest retrieval. Only then mark it **completed off-host**, retaining the original cut time. If transfer fails, the previous recovery point remains current. Keep and retry the staged copy, and alert on backup age.
7. **Apply retention.** Apply retention only to completed sets. Preserve the newest usable backup and required restriction evidence. Temporary staging copies also follow the deletion and retention policy.

The backup moves through these states:

```text
Backup in progress
    -> Complete, verified local copy; live service may resume
        -> Encrypted off-host transfer and verification complete
            -> New usable off-host recovery point
```

Only verified off-host completion advances the usable recovery point. Starting the job or finishing its local copy does not.

<a id="use-an-operator-managed-backup-tool-not-a-new-product-subsystem"></a>

### Use an operator-managed backup tool, not a new product subsystem

The proposed tool is a **pinned restic release writing to an existing operator-controlled SFTP destination**. SFTP transfers files over SSH. The recorded review used restic **0.19.1** documentation for encryption and SFTP support. That is historical evidence, not an already-tested Inframeld release pin.

Keep the backup passphrase or recovery key somewhere an authorized operator can recover it after host loss. It must be outside both the failed host and the encrypted backup it unlocks. Test that retrieval. No new software-as-a-service account or second SeaweedFS cluster is required.

<a id="separate-routine-repository-checks-from-reading-every-backup-byte"></a>

### Separate routine repository checks from reading every backup byte

A normal restic repository `check` does not read every stored data byte. Schedule data-integrity reads and actual restore rehearsals separately. `check --read-data` reads stored backup packs and needs additional time and bandwidth.

The one-hour transfer budget does **not** include rereading the entire retained repository every day.

Encryption protects backup contents, but a compromised writer may still delete them. The destination operator should control retained snapshots independently of application containers and test that protection. Also test integrity. Confidentiality, intact bytes, and protection from deletion are separate requirements.
