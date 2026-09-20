# ADR-0013: Production backup, restore, and deferred index reconstruction

**Status:** Accepted — provisional operating baseline for later validation. Backup/restore is required; product-level index reconstruction is deferred. **Revised:** 19 September 2026. **Required approach:** A documented, tested recovery procedure for the complete production Docker Compose installation, including current security checks before service resumes. **Related:** [Vector storage](ADR-0004-postgresql-source-of-truth-and-shared-chroma.md), [identity and authorization](ADR-0005-api-enforced-tenancy-and-authorization.md), [deployment](ADR-0011-hosted-vercel-and-aws-deployment-profile.md), [retention and deletion](ADR-0014-data-retention-deletion-and-external-processing.md).

## Context

Inframeld stores related state in several places. PostgreSQL holds application records and, in a separate database, Kratos identity data. SeaweedFS stores documents and processing artifacts through its S3-compatible interface. Chroma stores the numerical vectors used to search those documents. Configuration and encryption keys make the stored state usable.

Recovering only one component can leave the installation incomplete. The database might refer to an object that was not restored, or a retained pipeline might require an index that no longer exists. A **pipeline** retrieves document evidence and uses it to generate answers; its recorded configuration is not enough without the data it references.

From first principles, **safe recovery requires a matching set of data, the keys and configuration needed to use it, and a review of changes that happened after the backup**. Restoring old bytes must not silently restore a revoked permission, expose a deleted document, or repeat a model call that already incurred a charge.

This ADR covers recovery after loss of the installation’s durable data. A timed-out indexing request is a different failure: ordinary retries follow ADR-0004 and ADR-0007. **Restoring a backup is not the normal way to recover a candidate build.**

## Decision

**Require documented and tested backup/restore for production. Use a provisional daily cold-backup procedure: stop writers, copy a complete consistent installation into private local staging, restart service, then encrypt and transfer the frozen copy off-host.**

A **cold backup** copies the stores while they are stopped. **Local staging** is the temporary backup copy on the application host. **Off-host storage** must remain available when that host or its disk is lost; another directory on the same host does not provide that protection.

The scope and degree of certainty are different for each part of this decision:

| Part | Status |
| --- | --- |
| **Production backup and restore** | Required in v1, with documented procedures and successful recovery tests before production claims. |
| **Operating procedure and numerical targets below** | Accepted as a provisional planning baseline for later validation and refinement. They are not measured guarantees or a production service-level agreement (SLA). |
| **SeaweedFS as the S3 service** | Selected for v1. Its data and metadata belong in the recovery set. |
| **Product-level index reconstruction** | Deferred, including retained numerical embedding archives, a reconstruction API/UI, and a general reconstruction framework. |

Preserve `ArtifactStore` and `VectorIndex`, the application-owned interfaces for artifact storage and vector indexing. This decision does not introduce another recovery platform or change those boundaries. No throughput benchmark or restore rehearsal has yet validated this operating baseline.

### 1. Define recovery targets by the state they actually protect

The **backup cut** is the point in time represented by one consistent backup. Its **completion time** is when the encrypted off-host set has finished transferring and passed the required checks. Record both: they answer different questions.

The **recovery-point objective (RPO)** describes the target age of recoverable data. The **recovery-time objective (RTO)** describes the target time to restore and validate service under stated conditions. Neither is zero for this single-host installation.

#### Provisional workload, schedule, and targets

Every value below is a planning assumption or objective, not tested capacity.

| Planning input or objective | Proposed value and meaning |
| --- | --- |
| **Initial workload** | ADR-0004’s unmeasured workload: **25,000 documents**, approximately **500,000 current vectors**, one embedding profile, limited retained revisions, and remote model inference. An embedding profile identifies how numerical search vectors are produced and compared. |
| **Protected state** | Assume **100 GiB total** across PostgreSQL, SeaweedFS, Chroma, and configuration. This is an independent storage-budget assumption, not a conversion from vector count. Measure actual sources, histories, index overhead, and pending payloads. |
| **Backup schedule and outage** | Start a consistent cut every **24 hours**. Budget **20 minutes of planned unavailability** per backup. API queries, releases, and login are unavailable during the cold-copy phase. |
| **Local staging rate** | Assume **200 MiB/s effective verified copying**, including the work needed to trust the staged copy. Copying 100 GiB takes about **512 seconds / 8.5 minutes**, leaving roughly **11.5 minutes** for draining, stopping, manifest checks, and restart. Shared or slower disks may not achieve this. |
| **Off-host transfer rate** | Assume **50 MiB/s effective encrypted transfer**, including normal overhead. Transferring 100 GiB takes about **2,048 seconds / 34.1 minutes**. Target completed off-host protection within **one hour of the cut**; service can run during this transfer. |
| **Recovery point** | Target a **maximum 25-hour age of the latest completed off-host cut**, while daily backups and the one-hour completion budget succeed. A failed or missed backup increases exposure immediately. This is an operating/alert target, not a guaranteed bound. |
| **Recovery time** | Target **four hours from the operator beginning restoration to validated service reopening**, with the required replacement host, disk, matching images, keys, off-host access, and complete security evidence already available. |
| **Retention and rehearsal** | Propose **7 daily and 4 weekly completed sets**, a **monthly isolated restore**, and another rehearsal after material storage/schema changes. A schema is the database’s stored structure. Retention remains subject to ADR-0014’s deletion policy. |

The copy estimates use `100 × 1024 / 200` and `100 × 1024 / 50`, because one GiB contains 1,024 MiB. They estimate only the stated phases, not the complete recovery duration.

#### Keep the availability and disk costs visible

A 20-minute outage every day consumes approximately **10 hours per 30-day month**, before incidents or upgrades. This is a substantial limitation, not an incidental background task. A filesystem with tested snapshot support could later shorten the stop interval, but the portable baseline does not assume it. If the outage is unacceptable, revisit the backup mechanism explicitly rather than advertise unsupported availability.

Reserve **at least one additional complete backup-set size locally, plus growth headroom**. Do not fill the live volume to create its backup.

Without compression or deduplication savings, eleven 100-GiB retained sets require approximately **1.1 TiB remotely before headroom**; budget roughly **1.3 TiB**. Savings may help, but safety must not depend on them. Transfer and validation also compete with normal disk/network activity after service reopens.

#### Example: a partial transfer does not advance the recovery point

Monday’s backup cut is **02:00**, and its off-host transfer completes by **03:00**. Tuesday’s **02:00** backup is still transferring when the host fails at **02:50**.

The last usable off-host recovery point is **Monday at 02:00**, almost 25 hours old. It is not Monday at 03:00, and Tuesday’s incomplete set is not a successful installation backup even if some bytes reached the destination.

#### The four-hour recovery clock has explicit conditions

The target excludes incident detection, finding the operator, purchasing/provisioning replacement hardware, and an unavailable identity provider or model provider. It also depends on permission/deletion reconciliation being completed.

At the assumed rate, downloading 100 GiB already takes about **34 minutes**. Integrity checks, extraction, database/index startup, and application/security validation take additional time; retain the remaining budget as margin and measure each phase in rehearsal.

Restoring more data or manually establishing current permissions can exceed four hours. **Report the missed target rather than bypass security to meet it.**

### 2. Treat the complete backup set as one recovery unit

Each set has an **installation manifest**: an inventory describing what was backed up and how to restore it.

Record the common cut time, backup ID, software image digests, schema/format versions, file checksums, storage paths, file ownership and access modes, restore instructions, and security-review coverage. An image digest identifies exact container-image content; a checksum helps verify copied bytes. Keep the manifest with the encrypted set and record successful cut/completion timestamps separately.

**Do not mix yesterday’s PostgreSQL with today’s artifact or vector directories.** The following state belongs to one matching set:

| State | Required contents and purpose |
| --- | --- |
| **Complete PostgreSQL cluster** | The application **and Kratos databases**, roles/grants, transaction state, write-ahead log (WAL), and configuration outside the data directory. This preserves projects/groups, service-token verifiers, jobs/attempts, answer receipts and idempotency records, artifact keys/checksums, index layouts/membership/readiness, and current/candidate/previous Deployment pointers. A Deployment selects which pipeline version serves requests. An application-only dump omits identity and cluster roles. |
| **SeaweedFS namespace and data** | The entire configured filer store, volume directories, and master state, including the private/internal namespace. The proposed paths are `/data/filer`, `/data/volume`, and `/data/master`; include every directory actually configured, not just those example names. |
| **Chroma persistence** | The complete persistent directory for the selected server version: collection/system state, SQLite/WAL where used, vector index files, and metadata. Include every physical shard and profile referenced by retained releases and unfinished work. A shard is a physical partition of the index. Embeddings alone, collection names, or one SQLite file are not a complete restore. |
| **Protected configuration and recovery secrets** | Compose/configuration files and exact dependency pins; PostgreSQL, Kratos, and SeaweedFS credentials; Kratos schemas, cookie/cipher secrets, and OIDC client registration/configuration/secret; TLS certificates/keys or a tested reissue path; model/provider credentials or restore references; application encryption and idempotency-fingerprint keys, including required versions. Back up operator-managed secret files even when Compose mounts them under `/run/secrets`. |
| **Pending work and retention evidence** | Durable job/attempt records, bounded pending payloads required for safe write retries, deletion tombstones, and retention/pin state. Preserve original statuses as evidence. Recovery also needs the separately maintained newer restriction evidence described in Section 6. |

**WAL** records database changes needed by the database’s recovery process. **OIDC** is the external sign-in protocol; **TLS** protects HTTPS connections. An **idempotency record** identifies a repeated application request, and its fingerprint key supports safe request matching. A **tombstone** records a retired/deleted identity; a **pin** records that retained or active work still needs a resource.

These records are part of recovery state. A backup does not turn an interrupted request into a completed job.

### 3. Preserve each store’s complete on-disk representation

#### PostgreSQL: copy the whole stopped cluster

For this first operating model, use a cold copy of the **whole PostgreSQL cluster**—the complete database instance, not selected tables or just the application database.

Restore with the same PostgreSQL major version, architecture, and compatible image/configuration. Do not introduce external **tablespaces**, separate locations for database files, in the initial supported profile. If an installation uses them, include every target and any external WAL path.

The source’s PostgreSQL 18 references describe shutdown for ordinary file copying and why individual database/table files are insufficient. A future logical-dump procedure would need explicit coverage of roles and other cluster-wide state; it is not substituted here.

#### SeaweedFS: preserve the map and the bytes together

SeaweedFS’s **filer** stores its namespace: object/directory names, attributes, and the ordered chunks making up an object. Each chunk reference includes a volume ID, file key/cookie, offset, and size, and may reference a chunk manifest or encryption metadata. These are storage-chunk references, not Inframeld’s text excerpts used for retrieval.

For example, S3 object `artifacts/source-123` may resolve through the filer bucket namespace to chunks in **volumes 7 and 8**. Keeping only those volume files loses the map from the S3 key to the bytes. Keeping only the filer entry leaves a map to missing bytes.

With ADR-0011’s embedded LevelDB2 configuration, `/data/filer` contains the metadata store, including internal partitions, logs, and manifests. Preserve its **whole tree**, not an export of visible bucket names.

Preserve volume IDs and all files in the configured volume/index directories, including `.dat`, `.idx`, and applicable companion files. Do not rename or reallocate volume IDs during restore. Also retain master metadata, `filer.toml`, `master.toml`, `volume.toml`, and `security.toml` where present, static S3 identity configuration, and configured encryption keys.

Copy these paths while SeaweedFS is stopped. The provisional choice is a complete stopped-directory copy, not separate asynchronous metadata and volume backup mechanisms.

#### Chroma: use the deployed configuration as the inventory

The inspected Chroma 1.5.9 local implementation has persistent configuration and separate local index state. Generate the backup inventory from the deployed configuration and verify it against that server version; do not assume an old example’s default directory is complete.

The recorded PostgreSQL, SeaweedFS, and Chroma source links are retained in References. They support the inventory requirements, not a claim that Inframeld’s proposed 100-GiB restore has passed testing.

### 4. Follow the proposed backup sequence without overstating success

1. **Check prerequisites and mark the new attempt in progress.** The installation operator checks free space, off-host access, the latest successful cut, dependency versions, and the restriction register described in Section 6. Do not replace the previous successful-backup marker when a new job starts.
2. **Close admission and stop application activity.** Admission means accepting new work. Close public ingress, including Kratos public account changes, and stop new jobs. Drain bounded in-flight work, then conclusively stop the application, worker, parser, and Kratos processes. Resolve or record uncertain attempts under ADR-0004/0007. A client timeout does not prove a storage server stopped writing.
3. **Stop every store cleanly.** Stop Chroma, SeaweedFS, and PostgreSQL, wait for exit, and check shutdown results. Include background writers such as object compaction, which reorganizes storage internally. If graceful shutdown fails, fail the backup attempt and use the tested crash-recovery procedure before claiming a consistent cut. Never delete durable volumes or copy underneath a running store.
4. **Record the cut and copy the complete inventory.** With every writer stopped, copy into a new private staging directory, preserving ownership and access modes. Verify the inventory, checksums, and manifest. Sequential copies represent the same stable state because the stores remain stopped throughout; a filesystem snapshot is optional, not required.
5. **Restart and validate the live installation.** Restart the original stores and matching services. Check login, readiness, and a query against a retained release before reopening admission. Freeze staging against modification. Service can now resume, but **the new backup is not yet protected against host loss**.
6. **Encrypt, transfer, and verify off-host completion.** Transfer the frozen set outside the host’s failure domain. Check completion, repository integrity, and manifest retrieval before marking it **completed off-host**, retaining its original cut time. A transfer failure leaves the previous recovery point active. Keep/retry the staged copy and alert on backup age.
7. **Apply retention and record the result.** Apply retention only to completed sets. Preserve the newest usable set and required restriction evidence. Temporary staging copies also follow the deletion/retention policy.

The important state distinction is:

```text
Backup in progress
    -> Complete, verified local copy; live service may resume
        -> Encrypted off-host transfer and verification complete
            -> New usable off-host recovery point
```

Neither job startup nor local-copy completion advances the usable off-host recovery point.

### 5. Use an operator-managed backup tool, not a new product subsystem

The provisional tool recommendation is a **pinned restic release against an existing operator-controlled SFTP destination**. SFTP transfers files over SSH. The source inspected stable restic **0.19.1** documentation for encrypted repositories and SFTP support; this is not an already-qualified Inframeld tool pin.

Keep the repository passphrase/recovery key recoverable **outside both the failed host and the encrypted copy it unlocks**. Test that an authorized operator can obtain it. No new software-as-a-service account or second running SeaweedFS cluster is required.

#### Separate routine repository checks from reading every backup byte

An ordinary restic repository `check` is not a full read of all stored data. Schedule data-integrity reads and real restore tests separately. `check --read-data` reads repository packs—the stored backup-data files—and consumes additional time and bandwidth.

The one-hour transfer budget does **not** include rereading the entire retained repository every day.

Encryption also does not prevent a compromised backup writer from deleting backups. The destination operator should control retained snapshots and retention independently of application containers and test that protection. Encryption, integrity checking, and protection against deletion address different risks.

### 6. Reconcile newer restrictions before restored data becomes accessible

A backup contains historical permissions and deletion state. Suppose Monday’s backup allows Bob to read HR documents, and that access is removed on Tuesday. Restoring Monday must not authorize Bob again.

The same problem applies to deleted documents, disabled accounts, narrowed integration scope, revoked keys, and retention periods that have since expired. **A complete data restore is necessary, but not sufficient, for safe reopening.**

#### Keep a restriction/deletion register outside the server

The provisional procedure assigns one installation operator ownership of an **access-restriction/deletion register** in existing protected company storage outside the application server. It is a small operational record, not a new event-sourcing service or application journal platform.

Project administrators record restrictive change requests **before applying them**. The operator records the affected scope, stable user/credential/document IDs, intended restriction, time, request/completion status, and reviewer.

Also record approved retention policies and their effective dates so automatic expiry can be reapplied during restore. Keep entries for at least as long as any retained backup they can restrict. A register copy associated with an old backup does not replace the newer evidence needed to reconcile that backup.

An application audit export can help. However, a daily export from the same failed host cannot prove that all later changes survived. The operator must attest coverage **from the selected cut through the incident**, including outstanding requests and every administrator authorized to change access.

This is manual work with a risk of mistakes, not an automatic durability guarantee. If the burden is unacceptable, consider a narrow automatic off-host restriction record through a separate decision; do not silently add a journal platform.

#### Apply current security before reads, jobs, or credential reissue

Keep ingress closed while reconciling the restored installation:

| Area | Required restore behavior |
| --- | --- |
| **Human sessions and CI/integration credentials** | Invalidate the restored sessions and credentials. Reissue fresh, scoped credentials only after authorization review. CI credentials are those used by authorized automation. |
| **Accounts and local login credentials** | Review disabled identities and account-security changes. Where current credentials cannot be established safely, require controlled recovery/reset before enabling the account. |
| **Document and integration access** | Reapply narrower memberships, document allowlists, and integration ceilings—the maximum document scope an integration may use. |
| **Deletion and retention** | Reapply newer deletion tombstones and current retention expiry before retrieving or releasing content. |
| **Queued work** | Do not execute normal queued work under a historical authorization decision. Review it as described in Sections 7–8. |

**Missing restriction evidence does not mean there were no restrictions.** Keep affected projects, data, or accounts inaccessible. If the affected scope cannot be identified, keep the entire installation inaccessible.

An authorized owner must review retained content and reapprove current permissions before access resumes. Uncertain deletion status requires an explicit, recorded decision about that content, not merely fresh login. Invalidating credentials alone cannot establish that a restored document was not deleted after the cut.

The four-hour recovery target is conditional on this reconciliation. It may be missed safely rather than met by reopening uncertain access.

### 7. Restore privately, validate, then reopen only safe scopes

1. **Record the incident and isolate recovery.** Select a completed backup cut. Isolate the replacement host and ensure the old instance cannot resume serving or writing concurrently. Keep public ingress, jobs, and provider dispatch disabled. A DNS change only changes where a hostname resolves; it is not proof that the old process stopped.
2. **Retrieve and restore the matching set.** Verify the encrypted set and manifest, recover required keys, and restore every component to its recorded path with correct ownership. Start with matching supported image/schema versions. Do not combine disaster recovery with an untested upgrade or initialize new SeaweedFS volume IDs over restored data.
3. **Start stores privately and validate their relationships.** Check PostgreSQL and Kratos state, SeaweedFS namespace-to-volume references and checksums, and Chroma’s retained index dependencies. In bounded batches, verify artifact references and current/candidate/previous Deployment pointers. Missing dependencies remain unavailable; do not silently replace them by embedding again.
4. **Complete security reconciliation and access tests.** Apply Section 6 and test permitted and denied user/integration access. Verify that anonymous object access and internal administrative endpoints remain inaccessible. Exercise local login and configured OIDC login using current configuration.
5. **Classify unfinished work before enabling the worker.** Preserve original statuses as evidence, identify what can safely resume, and quarantine uncertain provider-capable work as `recovery_required`. A restored queued flag is not sufficient authority to execute it. Section 8 explains the distinction.
6. **Verify application behavior and record the recovery.** Query a known retained release and check its authorized evidence. In the isolated rehearsal, exercise a safe release transition and rollback. Verify gateway routing, current document permissions, deleted-content exclusion, and idempotency behavior. Record cut age, data loss, phase timings, checks, and exceptions. Reopen only validated scopes, then resume normal backups.

An uploaded object without a published application reference remains an **orphan**, not an admitted document. An interrupted candidate is not automatically ready. Published references must resolve to their required data before they can be treated as usable.

### 8. Do not replay uncertain work just because its completion was lost

A job marked `queued` at the backup cut may have called a model and completed afterward. Restoring the backup loses that later completion record, not necessarily the provider’s execution or charge.

For example:

```text
At the backup cut: job J is queued
After the cut:     J calls a model and completes
After host loss:   restore shows J as queued again
```

**The restored state does not prove the model call never happened.** Quarantine restored nonterminal provider-capable work as `recovery_required` unless its remaining work is positively proven safe. Nonterminal work has no recorded final outcome in the restored state. Preserve the backup’s original status as recovery evidence rather than erasing the history behind the classification.

A frozen vector insertion can have a safe replay path: the exact numerical payload is already captured, and ADR-0004 governs reinserting and verifying it. Repeating a model call to recover a lost result does not have that same proof.

Resume only work whose inputs, current permissions, and required retry payloads remain intact under the normal protocol.

#### Lost idempotency history limits duplicate detection

Idempotency records admitted after the cut may also be lost. A restored installation cannot promise duplicate detection for missing history or discover every external effect from that interval.

Clients and operators must reconcile saved operation IDs and pending workflows against the documented restore cut. Do not blindly restart a build/evaluation/release sequence. A deliberately new chargeable operation requires explicit authorization with the uncertainty visible.

This is a consequence of the accepted potential data-loss window. **The backup procedure does not provide exactly-once recovery of external operations across a disaster.**

### 9. Distinguish disposable trials from production recovery

Local trials use the same application and SeaweedFS topology. A trial user may explicitly choose disposable data and omit an off-host destination, provided the interface and documentation clearly state that **no production recovery target applies**.

A company production installation must configure the procedure, name its operator, and complete a restore rehearsal. A named Docker volume survives container replacement; it does not protect against losing its host disk.

Emit redacted structured logs and audit release, credential, permission, and deletion decisions in PostgreSQL. Redaction removes sensitive content from logs. Expose the latest completed backup cut and age, transfer failures, restore-test date, disk headroom, worker/queue health, and dependency failures.

An operator-readable status surface and **runbook**, written operating instructions, are sufficient. No mandatory telemetry warehouse, CloudWatch integration, or full tracing service is required.

### 10. Restore numerical indexes; do not claim to reconstruct them

Manifests, hashes, and source bytes explain an index’s inputs and structure. They do not contain the numerical vectors themselves.

If Chroma is lost and no usable backup contains its required persistence, mark affected releases unavailable and report the loss. **Do not silently re-embed historical releases.** Re-embedding invokes the model again and produces another numerical execution rather than recovering the stored vectors.

Future reconstruction needs a separate design for cost, retention/deletion, model drift, and isolated numerical lineage. Model drift means that the model’s behavior may differ from the earlier execution. Isolated numerical lineage means newly generated numerical output has distinct physical identities rather than overwriting retained output.

Creating an ordinary new pipeline version is not sufficient numerical isolation. Likewise, ADR-0004’s bounded retry payloads protect unfinished writes; they are temporary protocol data, not a complete retained numerical archive.

Product-level reconstruction, its API/UI, and a general framework remain deferred alongside high availability and additional distributed recovery infrastructure.

### 11. Rehearse host loss and security changes before production use

Before calling this profile production-ready, restore onto another host with representative state and failures:

| Acceptance case | Required result |
| --- | --- |
| **Complete host loss** | Recover the matching stores, configuration, and keys, including a pending attempt and retained rollback target. Validate the retained release and its evidence. |
| **Deletion after the cut** | Reapply the later deletion; the restored host must not disclose that content. |
| **Credential and group revocation after the cut** | Deny the revoked access after restoration, even when the backup still contains the earlier grants. |
| **Queued at the cut, paid/completed afterward** | Do not automatically call the model again. Preserve uncertainty and the original backup status, and require safe recovery classification. |
| **Corrupt/missing bytes or missing keys** | Produce a visible failure, not a successful backup/restore marker. |
| **Incomplete restriction evidence** | Keep unvalidated scopes inaccessible rather than assume unchanged permissions. |
| **Filled staging disk** | Fail visibly without reporting an incomplete set as a successful backup. |

Measure the **complete 100-GiB sequence**, downtime, effective copy/transfer rates, integrity checks, and restore phases. Refine storage, retention, and tool settings from those results. Repeat retained-release restoration, permission/deletion reconciliation, and safe handling of uncertain jobs.

Operator availability, ready replacement resources, recoverable keys, and off-host restriction evidence are material assumptions of the four-hour estimate.

**These tests remain to be performed.** Keep the provisional baseline until representative results justify changes. This ADR does not authorize a broader backup-design project or turn its estimates into production guarantees.

## Consequences

### Positive

- **Recovery protects a complete installation, not unrelated files.** One stopped, matching set includes application and identity state, object metadata and bytes, numerical indexes, pending-work evidence, and required configuration/keys.
- **The operating procedure stays limited and understandable.** Local cold-copy staging followed by encrypted off-host transfer avoids requiring a distributed snapshot system or a continuously replicated cluster. Service can resume during transfer.
- **Security and uncertain work remain explicit recovery concerns.** Reopening requires newer restrictions to be reconciled, and restored jobs cannot silently repeat chargeable calls merely because their completion records were lost.

### Negative

- **The provisional backup schedule causes substantial downtime.** Twenty minutes daily is about ten hours per 30-day month before other interruptions. A single host still needs replacement and restoration after host loss.
- **Protection consumes disk, bandwidth, and operator time.** Complete local staging, remote retention, transfer verification, key recovery, and recurring restore rehearsals have real costs. Neither compression nor optimistic throughput is a safety prerequisite.
- **Recovery targets depend on evidence and preparation.** Missing post-cut history limits deduplication; missing restriction evidence can prevent safe reopening. Manual reconciliation is fallible and may extend recovery beyond four hours. Lost vectors without a usable backup remain unavailable.

## Alternatives considered

No separate comparative evaluation is recorded. The following approaches are excluded, deferred, or not required by the selected baseline.

### Back up only PostgreSQL, object bytes, or selected index files

**Insufficient.** Application records, identity state, object namespaces, object bytes, and numerical indexes must remain consistent. An application database dump does not contain Kratos/global database state or SeaweedFS filer metadata. Object bytes without their namespace, or one Chroma SQLite file without the remaining index state, do not form the required installation backup.

### Copy live store directories or combine backups from different cuts

**Not the selected procedure.** The portable baseline stops every writer, including store background writers, before copying. It does not assume that copying live files or combining different component dates produces a consistent installation.

Tested filesystem snapshots could later shorten the stop interval. If the daily outage is unacceptable, explicitly revisit that mechanism rather than silently assume snapshot support or uninterrupted service.

### Introduce distributed recovery or database-only point-in-time recovery

**Not required for v1.** No distributed snapshot coordinator, continuously replicated cluster, event platform, or PostgreSQL-only point-in-time recovery is selected. Point-in-time recovery restores database state to a chosen point using its recovery history; it is not the complete multi-store procedure chosen here.

Keep the existing application/storage boundaries and the operator-run baseline. High availability and additional distributed recovery infrastructure remain outside scope.

### Trust restored credentials, permissions, and queued-job flags without review

**Ruled out.** Those records describe the backup cut, not every later change. Restored sessions and CI/integration credentials are invalidated; newer access restrictions and deletions must be reconciled. Queued work may have executed after the cut and needs an explicit safe-resume decision.

A fresh login does not resolve uncertain deletion history, and a new worker does not establish that an earlier provider call never happened.

### Reconstruct lost historical indexes instead of restoring their persistence

**Deferred.** Source bytes and manifests cannot recreate stored numerical embeddings by themselves. Product-level reconstruction and retained numerical archives need their own model-drift, cost, retention, and identity design. Ordinary exact-payload write retries are a separate capability, not a substitute for that archive.

## References

### Related decisions

| Reference | Responsibility |
| --- | --- |
| [ADR-0004: Vector storage](ADR-0004-postgresql-source-of-truth-and-shared-chroma.md) | Immutable vector generations, ordinary exact-payload retries, pending-write evidence, and the provisional workload. |
| [ADR-0005: Identity and authorization](ADR-0005-api-enforced-tenancy-and-authorization.md) | Kratos identity, integration credentials, and application-owned permissions. |
| [ADR-0007: Durable jobs and recovery](ADR-0007-durable-jobs-idempotency-and-recovery.md) | Safe retries, uncertain provider outcomes, operation identities, and deduplication limits. |
| [ADR-0011: Deployment](ADR-0011-hosted-vercel-and-aws-deployment-profile.md) | The supported single-server topology and explicit SeaweedFS storage layout. |
| [ADR-0014: Retention and deletion](ADR-0014-data-retention-deletion-and-external-processing.md) | Retention, deletion, and their application to backup and staging copies. |

### Recorded external evidence

These are the documentation and source references retained from the original ADR. They support the proposed procedure; they are not a new verification, approved dependency pins, or a completed Inframeld restore test.

| Reference | Evidence and limitation recorded in the source |
| --- | --- |
| **PostgreSQL 18:** [File-level backup](https://www.postgresql.org/docs/18/backup-file.html) and [cluster file layout](https://www.postgresql.org/docs/18/storage-file-layout.html) | Ordinary file copying requires shutdown and the complete cluster inventory. A later logical-dump approach needs separate role/global-state coverage. |
| **SeaweedFS 4.47:** [Filer data model](https://github.com/seaweedfs/seaweedfs/blob/4.47/weed/pb/filer.proto) and [S3 bucket-path discovery](https://github.com/seaweedfs/seaweedfs/blob/4.47/weed/command/s3.go) | Explain how object names map to ordered stored chunks and associated metadata. |
| **SeaweedFS 4.47:** [LevelDB2 filer store](https://github.com/seaweedfs/seaweedfs/blob/4.47/weed/filer/leveldb2/leveldb2_store.go) and [volume filename rules](https://github.com/seaweedfs/seaweedfs/blob/4.47/weed/storage/volume.go) | Support preserving complete metadata/volume directories and their recorded identities. |
| **SeaweedFS:** [Backup guidance](https://github.com/seaweedfs/seaweedfs/wiki/Data-Backup) | Separates volume and filer backups and requires changes to be paused for consistency. Its mirror example was tested only on a small deployment; it does not qualify this proposed 100-GiB recovery. |
| **Chroma 1.5.9:** [Configuration](https://github.com/chroma-core/chroma/blob/1.5.9/rust/frontend/src/config.rs) and [local HNSW persistence](https://github.com/chroma-core/chroma/blob/1.5.9/rust/segment/src/local_hnsw.rs) | Identify configuration and local index persistence that the deployed-version inventory must cover. |
| **restic, documentation inspected as 0.19.1:** [Repository setup](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html), [repository keys](https://restic.readthedocs.io/en/stable/070_encryption.html), and [integrity checks](https://restic.readthedocs.io/en/stable/045_working_with_repos.html) | Describe encrypted repositories, SFTP, recovery keys, and the difference between ordinary checking and `check --read-data`. Tool behavior and full recovery still need qualification. |
