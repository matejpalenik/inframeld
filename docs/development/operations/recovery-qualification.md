# Recovery Qualification

<a id="provisional-workload-schedule-and-targets"></a>

### Provisional workload, schedule, and targets

Every value below is a planning assumption or objective, not tested capacity.

| Planning input or objective | Proposed value and meaning |
| --- | --- |
| **Initial workload** | [Preparing and searching reliable indexes](../../../.agents/skills/inframeld-indexing/references/profiles-and-preparation.md)’s unmeasured workload: **25,000 documents**, approximately **500,000 current vectors**, one embedding profile, limited retained revisions, and remote model inference. An embedding profile identifies how numerical search vectors are produced and compared. |
| **Protected state** | Assume **100 GiB total** across PostgreSQL, SeaweedFS, Chroma, and configuration. This is an independent storage-budget assumption, not a conversion from vector count. Measure actual sources, histories, index overhead, and pending payloads. |
| **Backup schedule and outage** | Start a consistent cut every **24 hours**. Budget **20 minutes of planned unavailability** per backup. API queries, releases, and login are unavailable during the cold-copy phase. |
| **Local staging rate** | Assume **200 MiB/s effective verified copying**, including the work needed to trust the staged copy. Copying 100 GiB takes about **512 seconds / 8.5 minutes**, leaving roughly **11.5 minutes** for draining, stopping, manifest checks, and restart. Shared or slower disks may not achieve this. |
| **Off-host transfer rate** | Assume **50 MiB/s effective encrypted transfer**, including normal overhead. Transferring 100 GiB takes about **2,048 seconds / 34.1 minutes**. Target completed off-host protection within **one hour of the cut**. Service can run during this transfer. |
| **Recovery point** | Target a **maximum 25-hour age of the latest completed off-host cut**, while daily backups and the one-hour completion budget succeed. A failed or missed backup increases exposure immediately. This is an operating/alert target, not a guaranteed bound. |
| **Recovery time** | Target **four hours from the operator beginning restoration to validated service reopening**, with the required replacement host, disk, matching images, keys, off-host access, and complete security evidence already available. |
| **Retention and rehearsal** | Propose **7 daily and 4 weekly completed sets**, a **monthly isolated restore**, and another rehearsal after material storage/schema changes. A schema is the database’s stored structure. Retention remains subject to [Keeping and deleting data deliberately](../../../.agents/skills/inframeld-knowledge/references/deletion-and-retention.md)’s deletion policy. |

The copy estimates use `100 × 1024 / 200` and `100 × 1024 / 50`, because one GiB contains 1,024 MiB. They estimate only the stated phases, not the complete recovery duration.

<a id="rehearse-host-loss-and-security-changes-before-production-use"></a>

### Rehearse host loss and security changes before production use

Before calling this profile production-ready, restore onto another host with representative state and failures:

| Acceptance case | Required result |
| --- | --- |
| **Complete host loss** | Recover the matching stores, configuration, and keys, including a pending attempt and retained rollback target. Validate the retained release and its evidence. |
| **Deletion after the cut** | Reapply the later deletion. The restored host must not disclose that content. |
| **Credential and group revocation after the cut** | Deny the revoked access after restoration, even when the backup still contains the earlier grants. |
| **Complete identity restoration** | Restore the matching Kratos/Hydra databases, registrations and recovery material. Verify old browser and CLI credentials cannot authenticate after required invalidation, then verify a fresh login resolves the same eligible principal and current permissions. |
| **Missing Hydra state or unconfirmed cleanup** | Missing database/client/key material or a failed revocation step prevents reopening affected authenticated surfaces. Do not silently initialize replacement state or count Kratos-only cleanup as success. |
| **Identity migration or image rollback** | Exercise the exact supported Kratos/Hydra/UI release set. An older image that cannot safely use the migrated identity schema/state must not start as an automatic fallback. Preserve maintenance and use qualified recovery. |
| **Queued at the cut, paid/completed afterward** | Do not automatically call the model again. Preserve uncertainty and the original backup status, and require safe recovery classification. |
| **Corrupt/missing bytes or missing keys** | Produce a visible failure, not a successful backup/restore marker. |
| **Incomplete restriction evidence** | Keep unvalidated scopes inaccessible rather than assume unchanged permissions. |
| **Filled staging disk** | Fail visibly without reporting an incomplete set as a successful backup. |

Measure the **whole 100-GiB procedure**, including downtime, actual copy and transfer rates, integrity checks, and restoration. Use those results to refine storage, retention, and tool settings. Repeat restoration of a retained release, reapplication of permission/deletion changes, and review of uncertain jobs.

Operator availability, ready replacement resources, recoverable keys, and off-host restriction evidence are material assumptions of the four-hour estimate.

**These tests remain to be performed.** Keep the figures provisional until representative results support them. Recording estimates neither proves them nor selects a broader backup architecture.

<a id="keep-the-availability-and-disk-costs-visible"></a>

### Keep the availability and disk costs visible

A daily 20-minute outage adds up to **10 hours per 30-day month**, before incidents or upgrades. That is a substantial availability limitation. Tested filesystem snapshots might later shorten the stop interval, but the portable baseline does not assume them. If the outage is unacceptable, reconsider the backup method explicitly.

Reserve **at least one additional complete backup-set size locally, plus growth headroom**. Do not fill the live volume to create its backup.

Without compression or deduplication savings, eleven 100-GiB backups need approximately **1.1 TiB of remote storage before headroom**. Budget roughly **1.3 TiB**. Do not rely on savings for safety. Transfer and validation also consume disk and network capacity after the application reopens.

<a id="example-a-partial-transfer-does-not-advance-the-recovery-point"></a>

### Example: a partial transfer does not advance the recovery point

Monday’s backup cut is **02:00**, and its off-host transfer completes by **03:00**. Tuesday’s **02:00** backup is still transferring when the host fails at **02:50**.

The last usable off-host recovery point is **Monday at 02:00**, almost 25 hours old. It is not Monday at 03:00, and Tuesday’s incomplete set is not a successful installation backup even if some bytes reached the destination.

<a id="the-four-hour-recovery-clock-has-explicit-conditions"></a>

### The four-hour recovery clock has explicit conditions

The four-hour target starts when the operator begins restoring with the required resources available. It excludes detecting the incident, finding the operator, obtaining replacement hardware, and waiting for an unavailable identity or model provider. Reviewing and reapplying security restrictions is also required before reopening.

Downloading 100 GiB at the assumed rate already takes about **34 minutes**. Checking and extracting the backup, starting databases and indexes, and validating the application take longer. Keep margin for these steps and measure them during rehearsal.

Restoring more data or manually establishing current permissions can exceed four hours. **Report the missed target rather than bypass security to meet it.**
