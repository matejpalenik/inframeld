# ADR-0116: Apply bounded reviewed import plans through stable child operations

**Status:** Accepted

**Date:** 2026-10-29

## Context and Problem Statement

Import should apply exactly the configuration Bob reviewed and tell him which changes actually happened if a later step fails.

## Considered Options

- Use the focused bounded contract above. Selected.
- Reconstruct a plan from current destination state after interruption, increasing equivalence and retargeting risk.

## Decision Outcome

Apply the [complete accepted PD-CONTRACTS-04 contract](../../.agents/skills/inframeld-application-contracts/references/decision-import-review-and-recovery.md#approved-resolution). It owns the exact behavior, bounds, current-state checks and failure outcomes. Use a durable bounded reviewed action plan. Its identity binds the installation/target/account/Project, supported canonical definitions and content digest, typed-name-to-destination-ID mappings, exact create/reuse/update choices, preserve/apply policy choices, effective defaults/schema version, live-impact acknowledgments, relevant expected owner revisions and stable parent/child request identities. Persist original supported non-secret input before resource effects. Initial bounds are 1000 resource files,1 MiB per file,10 MiB total decoded input and a 2000-action plan. Reject cycles, duplicate typed names, unknown fields/kinds/versions and unsupported semantics before admission. No executable templates, overlays, environment interpolation or provider/asset download occurs during offline validation.

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Consequences

The plan needs explicit identities and per-owner outcomes. It avoids an elaborate provisioning engine and the false promise that a multi-step import is globally atomic.

An import creates two resources, then its Pipeline update conflicts with Alice's newer revision. Keep the two resources and stop the stale update. A new review can use those resources without creating duplicates.

Implementation, measured support and qualification remain separate. A chosen threshold is not a measured result. No application code, public endpoint or passing runtime evidence is delivered here.

## Links

- [Owning contract](../../.agents/skills/inframeld-application-contracts/references/decision-import-review-and-recovery.md#approved-resolution)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
