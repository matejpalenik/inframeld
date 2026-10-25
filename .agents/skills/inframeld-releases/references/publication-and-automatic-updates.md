# Publish ready versions under current authority

Alice starts an automatic handbook update, then switches Production to Manual. Preparation can still be useful, but that old request must not move traffic. Releases keeps preparation, publication authority and competing operator choices separate.

## Deployment state and authority

A Deployment selects ready PipelineVersions using current, candidate and designated previous pointers.

Manage releases is one exact-Deployment action covering publication, canary control, rollback, mode switches and automatic input selection. It replaces older Publish/deploy terminology. Build, Delete and non-serving configuration Edit remain separate.

Human creation uses project Create Deployment and atomically records the ready initial version, Deployment and explicit creator grants. The reviewed catalogue assigns thirteen Pipeline and seven Deployment creator actions, including separate query/evaluation inspection and own-feedback authority. Creator history never overrides later removal, and existing resources receive no automatic backfill.

Private starter provisioning explicitly makes its creator both group member and manager. That supplies neither Build nor release authority by itself.

Before the first default Deployment exists, the default binding holds its publication mode/control revision and stays not-ready. Do not create a fake version. First publication transfers that state atomically through its separate creation checks.

## Follow automatic publication

1. Admit a complete authorized live-input batch or explicit policy-controlled CLI Build. Require the underlying input/mutation rights, Pipeline Build and target Manage releases. Before default creation, onboarding instead needs project Create Deployment.
2. Capture exact selected configuration/corpus and publication-control state. Document-triggered updates use Deployment-selected configuration rather than the evolving Pipeline working copy.
3. Run normal readiness-only preparation. Edits, restores, direct queries and evaluation do not publish or supersede pending publication. Partial inputs and upload-only rights are insufficient.
4. Before dispatch and publication, recheck current authority. Publication checks newest authorized request identity, control revision, selected inputs, current attempt and serving state together.
5. Conditionally change traffic. A stale or failed request leaves healthy current in place. Superseded work cannot become fallback after a newer request fails.

The explicit CLI coordinator selects a sole live Deployment or asks for a choice among several. Never fan out. With none, ordinary Build stays unpublished while the existing first-publication path retains its distinct authority. A competing creation cannot authorize an update to somebody else's existing Deployment.

## Mode changes and races

The default onboarding path starts Automatic updates. Explicit new Deployments default Manual releases with an explicit automatic option. Mode belongs to each Deployment, not every Deployment of a Pipeline.

Automatic to Manual advances control revision and invalidates pending publication while allowing useful preparation to finish.

Manual to Automatic freezes selected inputs and admits fresh work. Even a 0% attached candidate blocks the switch. Re-enabling starts by reviewing the currently serving version's configuration, with any different saved selection explicit.

Off/on cannot revive an old job. The new admission has new publication authority rather than restoring the authority invalidated by the earlier switch.

Shared connection administration can change live connectivity even in Manual mode. It has separate current authority and backend review. Pipeline rollback does not restore connection access settings or credentials. Reject incompatible/unproven shared embedding changes before mutation. Use another connection and the ordinary query/build/release path for an isolated migration.

## Status and sources

Publication modes and concurrency guards are accepted design. Scores, feedback, synthetic tests and healthy historical labels are not release authority. Current erasure or unusable dependencies can invalidate targets. Exact action/wire mapping and runtime qualification remain with the guides and delivery plan.

- [Publication modes](../../../../docs/development/pipelines-and-releases.md#modes), [Pipelines and Releases](../../../../docs/development/pipelines-and-releases.md), [Release records](../../../../docs/development/data-model.md#releases), [onboarding](../../../../docs/development/onboarding.md), [Access](../../../../docs/development/access-control.md) and [creator assignments](../../../../docs/development/access-contracts.md#initial-assignments).
- [Jobs and idempotency](../../../../docs/development/jobs-and-idempotency.md), [shared connections](../../../../docs/development/model-connections.md#shared-current), [ADR-0033](../../../../docs/adr/ADR-0033-separate-build-readiness-from-release-authority.md), [ADR-0040](../../../../docs/adr/ADR-0040-bind-pipeline-versions-to-verified-profile-specific-materializations.md), [ADR-0047](../../../../docs/adr/ADR-0047-support-reversible-publication-modes-per-deployment.md) and [ADR-0054](../../../../docs/adr/ADR-0054-use-shared-current-model-connections.md).

## Pending decisions for dependent implementation

The ordinary behavior above remains owned by its current sources. Before choosing an unresolved implementation contract, load only the matching entry:

- [PD-RELEASES-01: Persist Deployment transitions with one shared control check](decision-deployment-state-and-concurrency.md). Before defining Deployment aggregate/repository state or implementing publication, mode changes, promotion, rollback or first binding.
- [PD-KNOWLEDGE-01: Finalize a complete collection selection without losing admitted input](../../inframeld-knowledge/references/decision-complete-batch-handoff.md). Before implementing batch completion, collection selection, parent/child recovery or the ingestion-to-automatic-update handoff.
- [PD-ACCESS-06: Authorize setup details before a Deployment exists](../../inframeld-access-models/references/decision-setup-read-authority.md). Before defining defaults/setup read contracts or implementing HTTP/MCP/CLI prepublication status resolution.
