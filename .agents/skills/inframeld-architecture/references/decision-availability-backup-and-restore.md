# PD-ARCHITECTURE-02: Match availability and recovery claims to the supported deployment

**Status:** PENDING

**Owner:** `inframeld-architecture`

**Issue kind:** Operating objectives and production qualification.

This reference supports a future discussion. Its recommendation is not accepted behavior. Current guides and ADRs retain authority.

## Contents

- [Problem and example](#problem-and-example)
- [Accepted context and evidence](#accepted-context-and-evidence)
- [Alternatives and trade-offs](#alternatives-and-trade-offs)
- [Non-binding recommendation](#non-binding-recommendation)
- [Decision trigger and stopping boundary](#decision-trigger-and-stopping-boundary)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Open questions and required evidence](#open-questions-and-required-evidence)
- [Sources and finalization](#sources-and-finalization)

## Problem and example

Production stops for its coordinated cold backup. Later the host fails and Alice must restore application, identity, artifact, vector, key and restriction state together. A restored revoked key or erased source must not become usable merely because the backup predates its restriction.

The provisional backup method and security reconciliation are selected. Actual outage, resource costs, supported availability and recovery objectives remain unqualified. A four-hour restore target that begins with the operator and resources ready is not a four-hour total incident downtime promise.

## Accepted context and evidence

Preserve one-server Compose and the coordinated installation backup: PostgreSQL application/Kratos/Hydra state, storage metadata/bytes, Chroma, keys/configuration and pending obligations. Cold-copy and off-host completion are distinct. Existing restore restrictions fail closed when required evidence is unavailable.

The current planning budget is a 20-minute daily outage, a conditional 25-hour recovery point and four hours from prepared operator restoration to validated reopening. At the full daily outage allowance, planned downtime alone is ten hours per 30-day month, about 98.6% availability before incidents/upgrades. These are assumptions and conditional arithmetic, not measured service levels. The manual off-host restriction register is provisional, not a new automated subsystem.

## Alternatives and trade-offs

1. **Qualify the existing cold-backup baseline for modest availability needs.** Measure drain/copy/restart/transfer/restore and rehearse restrictions on the supported host. This preserves a portable simple procedure, but accepts its measured downtime and operator burden.
2. **Revisit the backup/availability design only if objectives reject the baseline.** Gather evidence for a shorter interruption or another explicitly approved method. This may support higher availability, but requires a separate decision and tested consistency guarantees. It does not silently replace the accepted baseline.

## Non-binding recommendation

**Proposal only.** Qualify the selected baseline first and state an explicit availability expectation that fits it. If the intended objective cannot fit the measured interruption, raise a superseding decision before promising it. Do not imply HA or select snapshots without evidence.

## Decision trigger and stopping boundary

When setting availability/recovery objectives, assembling the production topology or qualifying backup, upgrade, security clearance and restore claims.

Clarify unselected objectives when needed. Missing production/recovery evidence blocks release claims, not authorized implementation/qualification of the accepted baseline.

## Architectural impact and dependencies

Deployment/runtime profile, operator runbooks, identity recovery, secret files, storage restoration, schema/job compatibility and restriction reapplication. Update backup/restore sequences only for the actual approved procedure.

Load neighboring decisions only under these conditions:

- [PD-ACCESS-03: Prove recovery cleanup before releasing product access](../../inframeld-access-models/references/decision-recovery-production-completion.md). For unfinished production identity-recovery integration.
- [PD-ACCESS-05: Implement and qualify the selected provider-secret lifecycle](../../inframeld-access-models/references/decision-provider-secret-lifecycle.md). For root-key/credential-store recovery.
- [PD-INDEXING-04: Qualify frozen storage retries and final erasure barriers](../../inframeld-indexing/references/decision-storage-retries-and-erasure.md). For storage late-write and erasure completion evidence.
- [PD-ARCHITECTURE-01: Select a measured supported workload and resource envelope](decision-supported-operating-envelope.md). For the workload and disk budget being qualified.

## Open questions and required evidence

- What availability objective do first users require, including planned maintenance?
- What measured drain/copy/reopen and off-host completion time does the host achieve?
- Who supplies keys, replacement resources and complete restriction evidence?
- Can the provisional register be rehearsed with multiple administrators and expired credentials?
- Which assembled readiness, dependency/security clearance and crash/restore checks remain outstanding?

## Sources and finalization

- [Provisional backup and restoration](../../../../docs/development/operations/upgrades.md).
- [Supported topology and security qualification](runtime-deployment-and-storage.md).
- [Backup decision](../../../../docs/adr/ADR-0038-recover-from-a-coordinated-backup-of-the-installation.md).
- [Deletion and backups](../../inframeld-knowledge/references/deletion-and-retention.md).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
