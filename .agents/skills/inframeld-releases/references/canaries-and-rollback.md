# Try a candidate, promote it or roll back

Production serves A, retains Z as previous and has ready candidate B. Alice wants to try B with a small audience before promotion. Candidate rejection and rollback have different pointer effects and must not be treated as interchangeable undo commands.

## Cohorts are routing, not identity

Authenticate and authorize first. Stable principal and rollout identities participate in the canary bucket. The affinity key is routing input, not permission or verified end-user delegation.

A shared application account remains one principal. Rotating its key or increasing the percentage must not reshuffle existing callers. Ten percent describes a share of identities, not an exact request count.

Use the guide's deterministic assignment contract rather than inventing another hash or per-request random choice. Preserve bounded candidate identity, selected version and receipt attribution. A 0% candidate is still attached and blocks switching to Automatic.

## Follow each transition

| Operation | Result |
| --- | --- |
| Attach or adjust B | A remains current. B receives only the selected stable cohort. |
| Reject or abort B | A remains current and Z remains previous. B is detached. |
| Promote B | B becomes current and A becomes designated previous. |
| Roll back after promotion | Use the eligible designated previous target under the one-step contract. Consume that target. |

Canaries and rollback require Manual mode. A candidate blocks rollback under the selected contract.

Missing, erased or unhealthy targets cannot be replaced silently by another historical version. Report unavailable rollback without changing current.

Configuration restoration merely creates new working configuration history and is not a production rollback.

## Failures and concurrent commands

Every transition checks current target-specific release authority, readiness, usable dependencies and expected serving/control state. A stale command conflicts instead of overwriting another operator's decision. Failure preserves healthy current. Current permissions and source erasure apply even to retained versions.

Pipeline rollback does not restore shared model access settings or old credentials. A successful score or positive feedback may inform Alice but cannot authorize a transition or switch Automatic off by itself.

## Status and sources

These are accepted pointer/cohort rules, not evidence of a delivered canary engine or qualified load distribution. Explain A/Z/B outcomes separately and inspect implementation before claiming a transition exists.

- [Canary and rollback behavior](../../../../docs/development/pipelines-and-releases.md), [Release records](../../../../docs/development/data-model.md#releases), [Access](../../../../docs/development/access-control.md), [feedback attribution](../../../../docs/development/answer-feedback.md) and [maintainer checks](../../../../docs/development/pipelines-and-releases.md#maintainer-checks).
- [ADR-0032](../../../../docs/adr/ADR-0032-keep-canary-assignment-stable-for-the-same-caller-and-affinity-key.md) owns stable affinity. [ADR-0047](../../../../docs/adr/ADR-0047-support-reversible-publication-modes-per-deployment.md) owns mode boundaries. [ADR-0008](../../../../docs/adr/ADR-0008-preserve-immutable-versions-and-their-provenance.md) explains immutable lineage.
