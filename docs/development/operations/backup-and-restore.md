# Back up and restore a complete installation

<a id="state-recovery-assumptions-explicitly"></a>

<a id="targets"></a>

<a id="3-state-recovery-assumptions-explicitly"></a>

## Understand the recovery point

A backup has two useful times. The **cut** is the point in time its data represents. **Completion** is when the encrypted copy has finished transferring off-host and passed its checks. Record both.

The **recovery-point objective (RPO)** is the target age of the data you can recover. The **recovery-time objective (RTO)** is the target time to restore and validate service under stated conditions. This single-server design promises neither zero data loss nor instant recovery.

## Choose the procedure

- [Make a complete backup](backups.md): inventory, coordinated cut, encryption, transfer and checks.
- [Restore privately](restore.md): recover data, reapply restrictions and reconcile uncertain work before reopening.
- [Qualify recovery](recovery-qualification.md): workload assumptions, outage, recovery targets and rehearsals.

These are separate reading tasks. A successful file copy does not establish a secure or usable restore.

<a id="decision-and-reference-map"></a>

<a id="decision-map"></a>

<a id="9-decision-and-reference-map"></a>

## Decision and reference map

The stopped-copy procedure, restic/SFTP choice, schedule, outage, and targets are proposals to test. The supported versions and actual configuration determine what must be backed up. Recorded references: [PostgreSQL filesystem backup](https://www.postgresql.org/docs/18/backup-file.html), [SeaweedFS filer configuration](https://github.com/seaweedfs/seaweedfs/blob/4.47/weed/command/scaffold/filer.toml), and [restic checking](https://restic.readthedocs.io/en/stable/045_working_with_repos.html).

High availability, automatic restriction journaling, product-level index reconstruction, and permanent numerical archives remain deferred. Missing restriction evidence keeps affected scopes closed even if a recovery target is missed.

| Decision | Rationale |
| --- | --- |
| [ADR-0037](../../adr/ADR-0037-use-controlled-migrations-and-coordinated-maintenance-upgrades.md) | Use controlled migrations and coordinated maintenance upgrades. |
| [ADR-0038](../../adr/ADR-0038-recover-from-a-coordinated-backup-of-the-installation.md) | Recover from a coordinated backup of the installation. |
