# ADR-0122: Qualify cold-backup recovery and explicit maintenance objectives

**Status:** Accepted

**Date:** 2026-10-29

## Context and Problem Statement

A single host needs planned maintenance and a coherent recovery set. Copying old data back is unsafe if it also restores credentials or sources that were later revoked or erased.

## Considered Options

- Use the focused bounded contract above. Selected.
- Change to a lower-interruption backup design, requiring a separate consistency/recovery qualification.

## Decision Outcome

Apply the [complete accepted PD-ARCHITECTURE-02 contract](../../.agents/skills/inframeld-architecture/references/decision-availability-backup-and-restore.md#approved-resolution). It owns the exact behavior, bounds, current-state checks and failure outcomes. Retain the coordinated cold-backup baseline for the whole installation: application/Kratos/Hydra PostgreSQL state, SeaweedFS metadata/bytes, Chroma, configuration/keys, security generations, retired identities, uncertain accounting and unfinished obligations. Do not replace it with an unqualified hot-copy/snapshot or imply high availability. Drain controlled work, stop relevant writes/stores, take and verify a coherent cut, reopen only under the existing readiness/security conditions and complete the off-host copy independently.

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Consequences

Cold backups cause planned downtime and require operator preparation. The selected uptime/recovery objectives acknowledge that cost instead of suggesting HA or guaranteed four-hour total incident recovery.

Alice restores yesterday's backup after Bob erased a handbook. The restore must reapply that restriction before serving, even if it takes longer. Reopening quickly with erased text or an old key would be an incorrect recovery.

Implementation, measured support and qualification remain separate. A chosen threshold is not a measured result. No application code, public endpoint or passing runtime evidence is delivered here.

## Links

- [Owning contract](../../.agents/skills/inframeld-architecture/references/decision-availability-backup-and-restore.md#approved-resolution)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
