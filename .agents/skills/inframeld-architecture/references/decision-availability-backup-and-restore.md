# PD-ARCHITECTURE-02: Match availability and recovery claims to the supported deployment

**Status:** ACCEPTED on 2026-10-29 in [ADR-0122](../../../../docs/adr/ADR-0122-qualify-cold-backup-recovery-and-explicit-maintenance-objectives.md). Implementation and qualification remain separate delivery work.

**Owner:** `inframeld-architecture`

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Contents

- [Approved resolution](#approved-resolution)
- [Why and example](#why-and-example)
- [Implementation and required evidence](#implementation-and-required-evidence)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Historical context and alternatives](#historical-context-and-alternatives)
- [Sources and finalization](#sources-and-finalization)

<a id="non-binding-recommendation"></a>

## Approved resolution

Retain the coordinated cold-backup baseline for the whole installation: application/Kratos/Hydra PostgreSQL state, SeaweedFS metadata/bytes, Chroma, configuration/keys, security generations, retired identities, uncertain accounting and unfinished obligations. Do not replace it with an unqualified hot-copy/snapshot or imply high availability. Drain controlled work, stop relevant writes/stores, take and verify a coherent cut, reopen only under the existing readiness/security conditions and complete the off-host copy independently.

Select a cut every 24 hours, planned interruption objective at most 20 minutes and verified off-host completion within one hour from cut. Conditional completed-cut recovery point objective is 25 hours. Conditional recovery time objective is four hours from a prepared authorized operator and replacement resources/keys being ready through validated reopening, not total incident downtime. Initial availability objective is 98.0 percent over 30 days including planned maintenance, without a contractual SLA. These are chosen qualification targets, not measured achievements. Daily 20-minute interruption alone consumes ten hours per 30 days, so stronger uptime cannot be inferred from the topology.

Keep seven daily and four weekly completed sets, with ordinary oldest-copy target at most 35 days. Retain the newest usable set if replacement fails, explicitly record that retention exception and backup-age breach, and preserve matching restriction evidence for every retained set. Incomplete, unverified or not-off-host copies cannot advance the reported recovery point. Budget the existing 100 GiB complete-set planning bound, separate local full-set staging and approximately 1.3TiB usable off-host storage without assumed compression/deduplication savings. Check actual inventory sizes and reserved coexistence before each cut/transfer; storage exhaustion never authorizes deleting the last usable recovery set or safety register.

Assign a primary and backup operator through the deployment runbook. Require recoverable off-host keys/configuration and a complete restriction register covering all administrators and all retained backup intervals. The register is an operator obligation, not an invented automatic security system. Reapply erasure/revocation/suspension, reconcile human security generations, invalidate restored credentials as required, preserve uncertain paid-call classifications and unfinished recovery/cleanup, and verify exact required dependencies privately before reopening. Missing restriction coverage keeps affected scopes closed, or the entire installation if the scope cannot be determined. An older database is never proof that a previously revoked credential or erased source is valid again.

Read/verify repository integrity weekly and rehearse an isolated full restore monthly and after material storage/schema/security changes. Measure drain, copy, restart, off-host completion, replacement provisioning assumptions and final security reconciliation separately. Failure to meet a target is a reported qualification failure, not permission to skip reconciliation or change the objective silently.

Managed upgrades remain explicit, using the already accepted matching qualified CLI/runtime release policy. Ordinary start does not upgrade. Bind an upgrade to reviewed installed/target release and schema state, verify a coherent usable backup and required key/restriction inventory first, then use one controlled migration owner and staged restart/readiness checks. Interrupted upgrades report actual state and recover original progress; never claim completion from image replacement alone. Image rollback is allowed only when the previous image is compatible with the current schema/state. Otherwise restore the coherent set through the protected recovery procedure, including post-cut restrictions, rather than downgrading the database or credential generations blindly. No upgrade/backup run or migration is authorized by recording this policy.

## Why and example

A single host needs planned maintenance and a coherent recovery set. Copying old data back is unsafe if it also restores credentials or sources that were later revoked or erased.

Alice restores yesterday's backup after Bob erased a handbook. The restore must reapply that restriction before serving, even if it takes longer. Reopening quickly with erased text or an old key would be an incorrect recovery.

Cold backups cause planned downtime and require operator preparation. The selected uptime/recovery objectives acknowledge that cost instead of suggesting HA or guaranteed four-hour total incident recovery.

<a id="decision-trigger-and-stopping-boundary"></a>

## Apply the accepted contract

Use this contract when the original trigger matches. Do not ask for the same policy decision again. Concrete native methods, DTO names and physical schemas are implementation choices consistent with this contract and the repository conventions. Missing measurements, fixtures or assembled evidence block the affected qualification/support claim, not authorized implementation or isolated tests. A failed test is not permission to weaken an accepted safety boundary.

<a id="open-questions-and-required-evidence"></a>

## Implementation and required evidence

Complete coordinated backup/transfer inventory, real timing/space samples, off-host verification, operator/key loss, multi-admin restriction coverage, stale credentials, erasure across restore, failed transfers, isolated restore and interrupted/ incompatible-schema upgrade rollback.

These are required checks, not tests run or successful production evidence. No application edits, paid calls or production changes follow merely from recording this decision.

## Architectural impact and dependencies

Deployment/runtime profile, operator runbooks, identity recovery, secret files, storage restoration, schema/job compatibility and restriction reapplication. Update backup/restore sequences only for the actual approved procedure.

Load neighboring decisions only under these conditions:

- [PD-ACCESS-03: Prove recovery cleanup before releasing product access](../../inframeld-access-models/references/decision-recovery-production-completion.md). For unfinished production identity-recovery integration.
- [PD-ACCESS-05 (accepted): Implement and qualify the selected provider-secret lifecycle](../../inframeld-access-models/references/decision-provider-secret-lifecycle.md). For root-key/credential-store recovery.
- [PD-INDEXING-04 (accepted): Qualify frozen storage retries and final erasure barriers](../../inframeld-indexing/references/decision-storage-retries-and-erasure.md). For storage late-write and erasure completion evidence.
- [PD-ARCHITECTURE-01 (accepted): Select a measured supported workload and resource envelope](decision-supported-operating-envelope.md). For the workload and disk budget being qualified.

## Historical context and alternatives

The following preserves the earlier problem, context and options. Statements that a choice was open describe that earlier analysis. The approved resolution above now settles it.

<a id="problem-and-example"></a>

### Original problem and example

Historical analysis before this resolution.

Production stops for its coordinated cold backup. Later the host fails and Alice must restore application, identity, artifact, vector, key and restriction state together. A restored revoked key or erased source must not become usable merely because the backup predates its restriction.

The provisional backup method and security reconciliation are selected. Actual outage, resource costs, supported availability and recovery objectives remain unqualified. A four-hour restore target that begins with the operator and resources ready is not a four-hour total incident downtime promise.

### Original accepted context and evidence

Historical context before this resolution. Unchanged invariants still apply.

Preserve one-server Compose and the coordinated installation backup: PostgreSQL application/Kratos/Hydra state, storage metadata/bytes, Chroma, keys/configuration and pending obligations. Cold-copy and off-host completion are distinct. Existing restore restrictions fail closed when required evidence is unavailable.

The current planning budget is a 20-minute daily outage, a conditional 25-hour recovery point and four hours from prepared operator restoration to validated reopening. At the full daily outage allowance, planned downtime alone is ten hours per 30-day month, about 98.6% availability before incidents/upgrades. These are assumptions and conditional arithmetic, not measured service levels. The manual off-host restriction register is provisional, not a new automated subsystem.

### Considered alternatives and trade-offs

Historical options, resolved by the approved contract above.

1. **Qualify the existing cold-backup baseline for modest availability needs.** Measure drain/copy/restart/transfer/restore and rehearse restrictions on the supported host. This preserves a portable simple procedure, but accepts its measured downtime and operator burden.
2. **Revisit the backup/availability design only if objectives reject the baseline.** Gather evidence for a shorter interruption or another explicitly approved method. This may support higher availability, but requires a separate decision and tested consistency guarantees. It does not silently replace the accepted baseline.

## Sources and finalization

- [Provisional backup and restoration](../../../../docs/development/operations/upgrades.md).
- [Supported topology and security qualification](runtime-deployment-and-storage.md).
- [Backup decision](../../../../docs/adr/ADR-0038-recover-from-a-coordinated-backup-of-the-installation.md).
- [Deletion and backups](../../inframeld-knowledge/references/deletion-and-retention.md).

Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later change to this accepted policy. Qualification evidence must identify its artifacts, environment, failures and limits. This record does not fabricate implementation or a passing test.
