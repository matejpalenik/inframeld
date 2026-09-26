# Upgrading and recovering an installation

Use this guide before upgrading Inframeld or recovering a failed server. Assume Support has a completed Monday backup. On Tuesday, Alice loses access to a document and another document is deleted. Restoring Monday's files must not give her that access back or make the deleted content available again.

[Deployment](deployment.md) explains the services and durable storage. [Jobs](jobs-and-idempotency.md) explains which interrupted operations can be retried. [Retention and deletion](retention-and-deletion.md) defines the restrictions that restoration must preserve.

**Reading route:** read the upgrade sequence for a software change. For host loss, start with the backup inventory, then follow private restoration and the review of newer restrictions.

> **Design status:** Controlled maintenance upgrades and coordinated recovery are accepted. The backup tools, schedule, procedure details, and timing targets below are proposals requiring tests. This guide does not report a completed production restore.

## Contents

| Reader’s question | Start here |
| --- | --- |
| What must match an application release? | [1. Understand the compatibility boundary](#compatibility) |
| How do migrations and rollback work? | [2. Perform a controlled upgrade](#upgrades) |
| What do the recovery targets promise? | [3. State recovery assumptions explicitly](#targets) |
| Which state and keys belong together? | [4. Back up one complete matching set](#inventory) |
| When may a backup be marked successful? | [5. Create a usable off-host backup](#backup) |
| How do we avoid restoring revoked access? | [6. Reapply restrictions before reopening](#restrictions) |
| What may safely resume? | [7. Restore privately and classify unfinished work](#restore) |
| What must upgrade and recovery rehearsals prove? | [8. Maintainer checks](#maintainer-checks) |
| Why these choices, and what remains open? | [9. Decision and reference map](#decision-map) |

<a id="compatibility"></a>

## 1. Understand the compatibility boundary

API and worker releases must be compatible with the same stored data. That includes the database **schema**, its tables, fields, and relationships.

Record explicit versions for three kinds of stored data:

| Versioned representation | What it describes |
| --- | --- |
| **Database schema** | The structure of application data in the database. |
| **Job payload** | The stored instructions and inputs the worker uses to execute a job. |
| **Artifact format** | The structure of stored outputs, such as processing results or manifests. A manifest records an inventory of artifacts or source identities. |

If a new worker cannot understand an older job format, it must reject it safely. Connecting successfully to PostgreSQL does not mean it can interpret every stored job.

### Migrations have one execution owner

A **migration** changes the database's structure or stored representation. The operator runs it through one explicit command or job. A database migration lock prevents two migrations from running at once.

On startup, API and worker check compatibility and refuse incompatible state. They must not each try to migrate the shared database.

<a id="upgrades"></a>

## 2. Perform a controlled upgrade

Use this sequence for the initial supported upgrade:

1. **Stop accepting new work.** Put the installation into maintenance mode.
2. **Finish or safely stop current work.** Account for running requests and jobs, including vector writes and model calls whose outcome is unknown.
3. **Take a backup.** Follow the [coordinated backup procedure](#backup) before changing stored state.
4. **Run the migration once.** Use the operator-controlled command and its database lock.
5. **Start matching application versions.** Deploy compatible API and worker images for the resulting schema, job payloads, and artifacts.
6. **Check before reopening.** Resume normal traffic only after the upgraded installation passes its required readiness checks.

**Stopping incoming requests does not cancel a request already sent to another service.** A vector store or model provider may still complete work after the application stops waiting for it.

Use the [Indexing recovery rules](indexing.md) for uncertain vector writes and the [job rules](jobs-and-idempotency.md) for provider calls. Maintenance mode alone does not establish whether remote work finished or whether repeating it is safe.

<a id="prefer-additive-changes-migrate-representations-in-stages-when-needed"></a>

### Prefer additive changes and migrate representations in stages when needed

Prefer changes that preserve the old representation while introducing the new one. For example, add an optional column before removing a field that existing work still uses. This is an **additive change**.

When old and new representations need to coexist, use the following sequence:

| Phase | What happens |
| --- | --- |
| **Expand** | Add the new representation while keeping the old one available. |
| **Backfill** | Populate the new representation for existing records using bounded, resumable work. |
| **Verify** | Check the converted data before relying on it. |
| **Switch** | Change the application to use the new representation. |
| **Remove later** | Remove obsolete fields in a later release, not as part of the initial expansion. |

Convert existing data in limited-size steps and record progress so an interruption does not restart the whole conversion. This is what “bounded, resumable backfill” means.

Use this staged approach when old and new representations need to coexist. Updating both on every write, called **dual-writing**, is unnecessary when a maintenance window can handle the conversion safely.

### Treat application rollback as a compatibility decision

An **application rollback** returns to an earlier Inframeld software version, usually by starting its earlier container image.

It is safe only if that version supports the database schema, saved jobs, and artifact formats now present. The fact that the old container starts is not enough.

A **down migration** attempts to reverse a schema change. Do not assume it preserves data, or delete newer data merely to make an older application run.

A destructive change needs a separate migration review and a tested restore point, meaning a backup from which recovery has been demonstrated.

### A RAG pipeline rollback is a different operation

A **retrieval-augmented generation (RAG) pipeline** retrieves document evidence and uses it to generate an answer. A Deployment selects which pipeline version serves requests.

Rolling back a pipeline changes those pointers. It does not downgrade the Inframeld application, reverse a database migration, or solve an incompatibility between application code and persisted data.

### Worked example: an optional field can still affect rollback

Suppose **application release 2** adds an optional field used by new jobs. These release numbers refer to Inframeld software, not pipeline versions.

During maintenance, the migration adds the column **before release 2 starts**. The matching API and worker can then use it for release-2 jobs.

Returning to release 1 is safe only if it can ignore the added column and avoid executing release-2 jobs it cannot understand. An optional column alone does not prove rollback is safe. Check job and artifact compatibility as well.

If compatibility is unknown, keep maintenance mode enabled. Restore through the documented procedure or ship a newer release that fixes the problem using the current stored state. The latter is a **corrective forward change**.

**Do not assume that removing the new column through a down migration will preserve the newer data or make its jobs safe to execute.**

<a id="targets"></a>

## 3. State recovery assumptions explicitly

A backup has two useful times. The **cut** is the point in time its data represents. **Completion** is when the encrypted copy has finished transferring off-host and passed its checks. Record both.

The **recovery-point objective (RPO)** is the target age of the data you can recover. The **recovery-time objective (RTO)** is the target time to restore and validate service under stated conditions. This single-server design promises neither zero data loss nor instant recovery.

### Provisional workload, schedule, and targets

Every value below is a planning assumption or objective, not tested capacity.

| Planning input or objective | Proposed value and meaning |
| --- | --- |
| **Initial workload** | [Preparing and searching reliable indexes](indexing.md)’s unmeasured workload: **25,000 documents**, approximately **500,000 current vectors**, one embedding profile, limited retained revisions, and remote model inference. An embedding profile identifies how numerical search vectors are produced and compared. |
| **Protected state** | Assume **100 GiB total** across PostgreSQL, SeaweedFS, Chroma, and configuration. This is an independent storage-budget assumption, not a conversion from vector count. Measure actual sources, histories, index overhead, and pending payloads. |
| **Backup schedule and outage** | Start a consistent cut every **24 hours**. Budget **20 minutes of planned unavailability** per backup. API queries, releases, and login are unavailable during the cold-copy phase. |
| **Local staging rate** | Assume **200 MiB/s effective verified copying**, including the work needed to trust the staged copy. Copying 100 GiB takes about **512 seconds / 8.5 minutes**, leaving roughly **11.5 minutes** for draining, stopping, manifest checks, and restart. Shared or slower disks may not achieve this. |
| **Off-host transfer rate** | Assume **50 MiB/s effective encrypted transfer**, including normal overhead. Transferring 100 GiB takes about **2,048 seconds / 34.1 minutes**. Target completed off-host protection within **one hour of the cut**. Service can run during this transfer. |
| **Recovery point** | Target a **maximum 25-hour age of the latest completed off-host cut**, while daily backups and the one-hour completion budget succeed. A failed or missed backup increases exposure immediately. This is an operating/alert target, not a guaranteed bound. |
| **Recovery time** | Target **four hours from the operator beginning restoration to validated service reopening**, with the required replacement host, disk, matching images, keys, off-host access, and complete security evidence already available. |
| **Retention and rehearsal** | Propose **7 daily and 4 weekly completed sets**, a **monthly isolated restore**, and another rehearsal after material storage/schema changes. A schema is the database’s stored structure. Retention remains subject to [Keeping and deleting data deliberately](retention-and-deletion.md)’s deletion policy. |

The copy estimates use `100 × 1024 / 200` and `100 × 1024 / 50`, because one GiB contains 1,024 MiB. They estimate only the stated phases, not the complete recovery duration.

### Keep the availability and disk costs visible

A daily 20-minute outage adds up to **10 hours per 30-day month**, before incidents or upgrades. That is a substantial availability limitation. Tested filesystem snapshots might later shorten the stop interval, but the portable baseline does not assume them. If the outage is unacceptable, reconsider the backup method explicitly.

Reserve **at least one additional complete backup-set size locally, plus growth headroom**. Do not fill the live volume to create its backup.

Without compression or deduplication savings, eleven 100-GiB backups need approximately **1.1 TiB of remote storage before headroom**. Budget roughly **1.3 TiB**. Do not rely on savings for safety. Transfer and validation also consume disk and network capacity after the application reopens.

### Example: a partial transfer does not advance the recovery point

Monday’s backup cut is **02:00**, and its off-host transfer completes by **03:00**. Tuesday’s **02:00** backup is still transferring when the host fails at **02:50**.

The last usable off-host recovery point is **Monday at 02:00**, almost 25 hours old. It is not Monday at 03:00, and Tuesday’s incomplete set is not a successful installation backup even if some bytes reached the destination.

### The four-hour recovery clock has explicit conditions

The four-hour target starts when the operator begins restoring with the required resources available. It excludes detecting the incident, finding the operator, obtaining replacement hardware, and waiting for an unavailable identity or model provider. Reviewing and reapplying security restrictions is also required before reopening.

Downloading 100 GiB at the assumed rate already takes about **34 minutes**. Checking and extracting the backup, starting databases and indexes, and validating the application take longer. Keep margin for these steps and measure them during rehearsal.

Restoring more data or manually establishing current permissions can exceed four hours. **Report the missed target rather than bypass security to meet it.**

<a id="inventory"></a>

## 4. Back up one complete matching set

Each backup has an **installation manifest**, an inventory explaining what it contains and how to restore it.

Record its cut time, backup ID, image digests, schema and format versions, checksums, storage paths, file ownership and access modes, restore instructions, and security-review coverage. Digests identify exact images, while checksums help check copied files. Keep this inventory with the encrypted backup. Track successful cut and completion times separately.

**Do not mix yesterday’s PostgreSQL with today’s artifact or vector directories.** The following state belongs to one matching set:

| State | Required contents and purpose |
| --- | --- |
| **Complete PostgreSQL cluster** | The application **and Kratos databases**, roles/grants, transaction state, write-ahead log (WAL), and configuration outside the data directory. This preserves projects/groups, service-token verifiers, jobs/attempts, answer receipts and idempotency records, artifact keys/checksums, index layouts/membership/readiness, and current/candidate/previous Deployment pointers. A Deployment selects which pipeline version serves requests. An application-only dump omits identity and cluster roles. |
| **SeaweedFS namespace and data** | The entire configured filer store, volume directories, and master state, including the private/internal namespace. The proposed paths are `/data/filer`, `/data/volume`, and `/data/master`. Include every directory actually configured, not just those example names. |
| **Chroma persistence** | The complete persistent directory for the selected server version: collection/system state, SQLite/WAL where used, vector index files, and metadata. Include every physical shard and profile referenced by retained releases and unfinished work. A shard is a physical partition of the index. Embeddings alone, collection names, or one SQLite file are not a complete restore. |
| **Protected configuration and recovery secrets** | Compose/configuration files and exact dependency pins<br>PostgreSQL, Kratos, and SeaweedFS credentials<br>Kratos schemas, cookie/cipher secrets, and OIDC client registration/configuration/secret<br>TLS certificates/keys or a tested reissue path<br>model/provider credentials or restore references<br>application encryption and idempotency-fingerprint keys, including required versions. Back up operator-managed secret files even when Compose mounts them under `/run/secrets`. |
| **Pending work and retention evidence** | Durable job/attempt records, bounded pending payloads required for safe write retries, deletion tombstones, and retention/pin state. Preserve original statuses as evidence. Recovery also needs the separately maintained newer restriction evidence described in [Reconcile newer restrictions before restored data becomes accessible](upgrades-and-recovery.md#restrictions). |

**WAL** records database changes needed by the database’s recovery process. **OIDC** is the external sign-in protocol. **TLS** protects HTTPS connections. An **idempotency record** identifies a repeated application request, and its fingerprint key supports safe request matching. A **tombstone** records a retired/deleted identity. A **pin** records that retained or active work still needs a resource.

Recovery needs these records as well as the data. An interrupted request remains interrupted until its outcome is established.

### PostgreSQL: copy the whole stopped cluster

The initial proposal copies the **whole PostgreSQL cluster while it is stopped**. Here “cluster” means the complete database instance, including its databases and shared state. It does not mean a multi-server installation.

Restore using the same PostgreSQL major version and architecture, with a compatible image and configuration. The initial supported setup has no external **tablespaces**, extra locations for database files. If an installation uses them, its inventory must include every location and any external WAL path.

The recorded PostgreSQL 18 references explain why ordinary file copying requires shutdown and why individual table or database files are insufficient. A future logical-dump procedure would need to cover roles and other shared state explicitly. It is not the procedure selected here.

### SeaweedFS: preserve the map and the bytes together

SeaweedFS needs both stored bytes and a map showing where each object's bytes are. The **filer** stores that map: object and directory names, attributes, and ordered storage chunks. Each chunk reference includes a volume ID, file key/cookie, offset, and size, and may refer to a chunk manifest or encryption metadata. These storage chunks are different from the text excerpts Inframeld retrieves.

For example, S3 object `artifacts/source-123` may resolve through the filer bucket namespace to chunks in **volumes 7 and 8**. Keeping only those volume files loses the map from the S3 key to the bytes. Keeping only the filer entry leaves a map to missing bytes.

With [Running the application on one server](deployment.md)’s embedded LevelDB2 configuration, `/data/filer` contains the metadata store, including internal partitions, logs, and manifests. Preserve its **whole tree**, not an export of visible bucket names.

Preserve volume IDs and all files in the configured volume/index directories, including `.dat`, `.idx`, and applicable companion files. Do not rename or reallocate volume IDs during restore. Also retain master metadata, `filer.toml`, `master.toml`, `volume.toml`, and `security.toml` where present, static S3 identity configuration, and configured encryption keys.

Stop SeaweedFS before copying these directories. The proposal copies the complete stopped state together rather than relying on independent background copies of metadata and volumes.

### Chroma: use the deployed configuration as the inventory

The recorded inspection of Chroma 1.5.9 found persistent configuration and separate local index state. Build the inventory from the deployed configuration and check it against the selected server version. An old example's default directory may be incomplete.

The [decision map](#decision-map) links the retained storage references. They do not establish that the proposed 100-GiB restore has passed testing.

<a id="backup"></a>

## 5. Create a usable off-host backup

1. **Check prerequisites.** Record a new backup attempt as in progress. Check free space, off-host access, dependency versions, the latest successful cut, and the [restriction register](#restrictions). Starting a new attempt must not replace the previous successful-backup marker.
2. **Stop new and running application work.** Close public ingress, including Kratos account changes, and stop accepting jobs. Allow limited time for running work to finish, then establish that API, worker, parser, and Kratos processes have stopped. Resolve or record uncertain attempts using the [Indexing](indexing.md) and [job](jobs-and-idempotency.md) rules. A client timeout does not prove a storage server stopped writing.
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

### Use an operator-managed backup tool, not a new product subsystem

The proposed tool is a **pinned restic release writing to an existing operator-controlled SFTP destination**. SFTP transfers files over SSH. The recorded review used restic **0.19.1** documentation for encryption and SFTP support. That is historical evidence, not an already-tested Inframeld release pin.

Keep the backup passphrase or recovery key somewhere an authorized operator can recover it after host loss. It must be outside both the failed host and the encrypted backup it unlocks. Test that retrieval. No new software-as-a-service account or second SeaweedFS cluster is required.

### Separate routine repository checks from reading every backup byte

A normal restic repository `check` does not read every stored data byte. Schedule data-integrity reads and actual restore rehearsals separately. `check --read-data` reads stored backup packs and needs additional time and bandwidth.

The one-hour transfer budget does **not** include rereading the entire retained repository every day.

Encryption protects backup contents, but a compromised writer may still delete them. The destination operator should control retained snapshots independently of application containers and test that protection. Also test integrity. Confidentiality, intact bytes, and protection from deletion are separate requirements.

<a id="restrictions"></a>

## 6. Reapply restrictions before reopening

A backup contains historical permissions and deletion state. Suppose Monday’s backup allows Bob to read HR documents, and that access is removed on Tuesday. Restoring Monday must not authorize Bob again.

The same problem applies to deleted documents, disabled accounts, narrowed integration scope, revoked keys, and retention periods that have since expired. **A complete data restore is necessary, but not sufficient, for safe reopening.**

### Keep a restriction/deletion register outside the server

The provisional procedure names one installation operator to maintain an **access-restriction/deletion register** in protected company storage outside the server. It is a small record of restrictions that recovery must reapply, not a new event-sourcing service.

Before applying a restrictive change, project administrators record its request. The operator records the affected scope, stable user, credential, or document IDs, intended restriction, time, request/completion status, and reviewer.

Record retention policies and their effective dates too, so recovery can reapply automatic expiry. Keep each entry as long as any retained backup might need it. Monday's copy of the register cannot establish what changed on Tuesday.

Audit exports can help, but a daily export from the failed host cannot prove that every later change survived. The operator must establish that the evidence covers the selected backup cut through the incident, including outstanding requests and every administrator who could change access.

This manual procedure can fail through human error. If maintaining it is impractical, a separate decision could introduce a narrowly scoped automatic off-host record. Do not quietly assume that such a system already exists.

### Apply current security before reads, jobs, or credential reissue

Keep public access closed while applying these checks:

| Area | Required restore behavior |
| --- | --- |
| **Human sessions and CI/integration credentials** | Invalidate the restored sessions and credentials. Reissue fresh, scoped credentials only after authorization review. CI credentials are those used by authorized automation. |
| **Accounts and local login credentials** | Review disabled identities and account-security changes. Where current credentials cannot be established safely, require controlled recovery/reset before enabling the account. |
| **Document and integration access** | Reapply narrower memberships, document allowlists, and integration ceilings—the maximum document scope an integration may use. |
| **Deletion and retention** | Reapply newer deletion tombstones and current retention expiry before retrieving or releasing content. |
| **Queued work** | Do not execute normal queued work under a historical authorization decision. Review it through [restore classification](#restore). |

**Missing restriction evidence does not mean there were no restrictions.** Keep affected projects, data, or accounts inaccessible. If the affected scope cannot be identified, keep the entire installation inaccessible.

An authorized person responsible for the affected scope must review retained content and reapprove current permissions before reopening. If deletion status is uncertain, record an explicit decision about that content. Requiring fresh login or invalidating credentials does not establish whether a document was deleted after the backup.

The four-hour recovery target is conditional on this reconciliation. It may be missed safely rather than met by reopening uncertain access.

<a id="restore"></a>

## 7. Restore privately and classify unfinished work

1. **Isolate recovery.** Record the incident and select a completed backup. Keep public ingress, jobs, and provider calls disabled. Establish that the old instance cannot resume serving or writing. Changing DNS alone does not stop an old process.
2. **Restore the matching set.** Verify the encrypted backup and manifest, recover the required keys, and restore every component to its recorded path with correct ownership. Use matching supported images and schema versions. Do not combine recovery with an untested upgrade or create new SeaweedFS volume IDs over restored data.
3. **Check stores privately.** Verify PostgreSQL and Kratos state, SeaweedFS namespace-to-volume references and checksums, and Chroma dependencies. In limited-size batches, check artifact references and current, candidate, and previous Deployment pointers. Keep missing dependencies unavailable. Do not silently replace lost vectors with a new embedding call.
4. **Reapply current restrictions.** Follow the [security review](#restrictions), then test both allowed and denied human/integration access. Anonymous object access and internal administrative endpoints must remain inaccessible. Test local login and any configured OIDC login using current settings.
5. **Review unfinished work.** Preserve original statuses as evidence. Identify safe resumptions and place uncertain work that can call a provider into `recovery_required`. A restored `queued` flag is not permission to execute it. The next section explains why.
6. **Check the application before reopening.** Query a known retained release and inspect its authorized evidence. During isolated rehearsal, try a safe release transition and rollback. Verify gateway routing, current document permissions, deleted-content exclusion, and idempotency. Record backup age, data loss, phase timings, checks, and exceptions. Reopen only validated scopes, then resume normal backups.

A stored object without a published application reference is still an orphan, not an admitted document. An interrupted candidate is still unfinished. Before using any published record, establish that its required data exists.

### Do not replay uncertain work just because its completion was lost

A job marked `queued` at the backup cut may have called a model and completed afterward. Restoring the backup loses that later completion record, not necessarily the provider’s execution or charge.

For example:

```text
At the backup cut: job J is queued
After the cut:     J calls a model and completes
After host loss:   restore shows J as queued again
```

**The restored record cannot prove that the model call never happened.** Unless the remaining work is positively known to be safe, put restored unfinished work that can call a provider into `recovery_required`. Keep its original backup status as evidence rather than replacing the history with the new classification.

Repeating a saved vector insertion can be safe because its exact numbers are already captured. Follow the [Indexing retry checks](indexing.md). A new model call to recover a lost answer does not have that same guarantee.

Resume only work whose inputs, current permissions, and required retry payloads remain intact under the normal protocol.

### Lost idempotency history limits duplicate detection

Request-idempotency records created after the backup cut may be lost too. Without them, the restored installation cannot recognize every repeated request or discover every external effect from that period.

Clients and operators must compare saved operation IDs and pending workflows with the known backup cut. Do not automatically restart a build, evaluation, and release sequence. Starting a new chargeable operation requires explicit authorization with the previous outcome's uncertainty visible.

The accepted data-loss window includes this limitation. **Disaster recovery cannot guarantee that each external operation runs exactly once.**

### Distinguish disposable trials from production recovery

Local trials use the same application and SeaweedFS topology. A trial user may explicitly choose disposable data and omit an off-host destination, provided the interface and documentation clearly state that **no production recovery target applies**.

A company production installation must configure the procedure, name its operator, and complete a restore rehearsal. A named Docker volume survives container replacement. It does not protect against losing its host disk.

Keep logs structured and remove sensitive values. Audit release, credential, permission, and deletion decisions in PostgreSQL. Show the latest completed backup cut and its age, failed transfers, last restore-test date, free disk space, worker and queue health, and dependency failures.

An operator-readable status view and a **runbook**, written operating instructions, are sufficient. V1 does not require a telemetry warehouse, CloudWatch, or a full tracing service.

<a id="restore-numerical-indexes-do-not-claim-to-reconstruct-them"></a>

### Restore numerical indexes and do not claim to reconstruct them

Manifests, hashes, and source bytes explain an index’s inputs and structure. They do not contain the numerical vectors themselves.

If Chroma is lost and no usable backup contains its required persistence, mark affected releases unavailable and report the loss. **Do not silently re-embed historical releases.** Re-embedding invokes the model again and produces another numerical execution rather than recovering the stored vectors.

Future index reconstruction needs its own design. It must account for cost, retention, deletion, and changes in model output over time. Newly generated numbers need distinct physical identities so they cannot overwrite retained results.

Creating a new PipelineVersion alone does not give those vectors distinct physical identities. The [saved batches used for vector retries](indexing.md) are also insufficient. They protect unfinished writes and are not a permanent archive of every published vector.

Product-level reconstruction, its API/UI, and a general framework remain deferred alongside high availability and additional distributed recovery infrastructure.

<a id="maintainer-checks"></a>

## 8. Maintainer checks

Use representative persisted jobs, source and artifact references, and Deployments. An upgrade test against an empty database alone does not exercise these compatibility requirements.

| Area | Required verification |
| --- | --- |
| **Upgrade** | Apply the upgrade against representative existing state and verify that the new API and worker can use it correctly. |
| **Migration ownership** | Verify migration locking and that API/worker startup cannot race to migrate the schema. |
| **Compatibility refusal** | Verify that incompatible startup is rejected and that the new worker safely rejects unsupported old job shapes. |
| **Backfill recovery** | Interrupt a backfill and verify that its bounded work can resume. |
| **Supported application rollback** | Exercise the claimed rollback path against persisted jobs, source/artifact references, and Deployments—not only the database schema. |
| **Restore** | Validate the documented restore procedure and the restore point required for destructive changes. |

These are acceptance conditions. The maintenance-upgrade approach is accepted, but implementation qualification has not yet been completed.

### Rehearse host loss and security changes before production use

Before calling this profile production-ready, restore onto another host with representative state and failures:

| Acceptance case | Required result |
| --- | --- |
| **Complete host loss** | Recover the matching stores, configuration, and keys, including a pending attempt and retained rollback target. Validate the retained release and its evidence. |
| **Deletion after the cut** | Reapply the later deletion. The restored host must not disclose that content. |
| **Credential and group revocation after the cut** | Deny the revoked access after restoration, even when the backup still contains the earlier grants. |
| **Queued at the cut, paid/completed afterward** | Do not automatically call the model again. Preserve uncertainty and the original backup status, and require safe recovery classification. |
| **Corrupt/missing bytes or missing keys** | Produce a visible failure, not a successful backup/restore marker. |
| **Incomplete restriction evidence** | Keep unvalidated scopes inaccessible rather than assume unchanged permissions. |
| **Filled staging disk** | Fail visibly without reporting an incomplete set as a successful backup. |

Measure the **whole 100-GiB procedure**, including downtime, actual copy and transfer rates, integrity checks, and restoration. Use those results to refine storage, retention, and tool settings. Repeat restoration of a retained release, reapplication of permission/deletion changes, and review of uncertain jobs.

Operator availability, ready replacement resources, recoverable keys, and off-host restriction evidence are material assumptions of the four-hour estimate.

**These tests remain to be performed.** Keep the figures provisional until representative results support them. Recording estimates neither proves them nor selects a broader backup architecture.

<a id="decision-map"></a>

## 9. Decision and reference map

The stopped-copy procedure, restic/SFTP choice, schedule, outage, and targets are proposals to test. The supported versions and actual configuration determine what must be backed up. Recorded references: [PostgreSQL filesystem backup](https://www.postgresql.org/docs/18/backup-file.html), [SeaweedFS filer configuration](https://github.com/seaweedfs/seaweedfs/blob/4.47/weed/command/scaffold/filer.toml), and [restic checking](https://restic.readthedocs.io/en/stable/045_working_with_repos.html).

High availability, automatic restriction journaling, product-level index reconstruction, and permanent numerical archives remain deferred. Missing restriction evidence keeps affected scopes closed even if a recovery target is missed.

| Decision | Rationale |
| --- | --- |
| [ADR-0037](../adr/ADR-0037-use-controlled-migrations-and-coordinated-maintenance-upgrades.md) | Use controlled migrations and coordinated maintenance upgrades. |
| [ADR-0038](../adr/ADR-0038-recover-from-a-coordinated-backup-of-the-installation.md) | Recover from a coordinated backup of the installation. |
