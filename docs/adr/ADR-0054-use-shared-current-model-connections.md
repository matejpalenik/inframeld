# ADR-0054: Use shared current model connections

**Status:** Accepted. Partially supersedes [ADR-0025](ADR-0025-separate-connection-meaning-from-replaceable-credentials.md) on consumer-pinned connection configurations and [ADR-0008](ADR-0008-preserve-immutable-versions-and-their-provenance.md) on freezing access configuration inside complete Pipeline configuration. Credential separation and immutable Pipeline, profile and vector history remain accepted.

**Date:** 2026-09-30

## Context and Problem Statement

Alice maintains `company-gateway`, used by several Pipelines. An authorized access-setting update should take effect for all its consumers without rebuilding every Pipeline. Engineers who need an isolated migration can instead create `company-gateway-next`, select it on a Pipeline, query/evaluate, then build and release.

Previously, retained Pipeline and profile configurations selected immutable semantic connection revisions. That protected historical access settings but allowed one connection identity to mean different active configurations to different consumers. It also complicated portable configuration exports. We now choose one shared current access configuration per connection, with explicit production-impact controls.

## Considered Options

- Retain consumer-pinned immutable connection revisions: stronger access-configuration isolation, but more revision selection and export complexity.
- Make access settings immutable and require another connection for each change: clear identities, but unnecessary migration work for shared infrastructure maintenance.
- Use shared current connections with reviewed updates and separate connections for staged migration: simpler operational ownership, with deliberate shared impact and weaker historical environment reproduction.

These are product trade-offs, not measured usability or runtime results.

## Decision Outcome

A connection has a stable project-owned identity and one current committed access configuration. Pipeline and evaluator definitions select that identity, not an old access revision. ModelGateway resolves current settings at dispatch. Non-secret access revisions remain available for audit, conflict detection, restoration proposals and actual execution attribution, not as runtime selectors.

Connection management owns supported provider/access settings. Pipeline configuration owns generation/reranking model selections and parameters. Embedding profiles own expected model identity and vector-space settings. Credentials have their separate replaceable lifecycle. All remote calls still use ModelGateway and embedded LiteLLM.

Connection-management authority includes reviewed live impact, without requiring Manage releases on every affected Deployment. Pipeline Edit alone does not grant it. Updates require current authorization, a complete reviewed diff, conditional revision/dependency checks and explicit acknowledgment when live consumers are affected. Manual release mode does not shield consumers from connection administration. Commit the complete update, required credential transition, audit and retry outcome together; never expose partially changed settings.

An in-place origin change is permitted only within operator destination policy and with explicit destination-bound credential provision, or an explicitly permitted credential-free configuration that removes the old credential. Never forward the saved secret implicitly. This replaces the guides' former new-connection-only rule, not [ADR-0024](ADR-0024-approve-outbound-destinations-before-model-calls.md)'s egress safeguards.

Reject shared updates before mutation if prepared or in-progress embedding data would become incompatible or compatibility cannot be established. V1 does not infer equivalence from matching dimensions, model aliases or a successful probe. Deliberate embedding-model changes remain supported through another appropriate profile/connection and ordinary preparation, direct Pipeline queries, Build and release. No confirmation bypass, automatic re-embedding or mixed-space retrieval is allowed.

Relevant access changes stop remaining model dispatches in an admitted multi-call operation rather than silently changing its inputs or continuing with historical access settings. Already-sent calls cannot be recalled. Credential-only rotation and metadata-only renaming do not constitute that access change. Preserve protected partial outcomes and uncertainty, and require new admission for changed access settings. Pipeline rollback never restores connection configuration or credentials.

## Consequences

- Shared connectivity has one current meaning. Configuration exports contain one current definition per connection, not variants selected by different Pipelines.
- An infrastructure update can affect production without a Pipeline build or publication. It needs independent administration controls and honest impact disclosure.
- Pipeline versions still freeze Pipeline settings and prepared-data bindings, but do not reproduce their historical access environment. Record actual connection/model observations on executions.
- Frozen evaluation runs and comparisons cannot quietly continue across relevant access changes. Historical connection observations do not authorize replay against an old configuration.
- Embedding identity checks cannot detect every unannounced provider-side alias change. Supported identity evidence and runtime shape checks need qualification; unknown compatibility is not approval for a shared update.
- No application code, physical schema, published wire contract or runtime guarantee is established by this ADR.

## Links

- [Model connections](../development/model-connections.md#shared-current) owns update, dispatch and restoration behavior.
- [Data model](../development/data-model.md#shared-current-connections) owns logical identities, revisions and observations.
- [Indexing](../development/indexing.md#embedding-compatibility) owns vector compatibility and preparation.
- [Shared-connection administration](https://github.com/matejpalenik/inframeld/issues/31) illustrates administration and gradual migration.
- [ADR-0050](ADR-0050-make-model-preflight-optional-and-record-runtime-validation.md), [ADR-0051](ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md) and [ADR-0052](ADR-0052-separate-experimental-execution-from-release-ready-pipeline-builds.md) retain optional tests, Ragas and the development loop with this shared-connectivity boundary.
- [Azure API Management backends](https://learn.microsoft.com/en-us/azure/api-management/backends) is a precedent for centrally editable reusable upstreams. [Azure API revisions](https://learn.microsoft.com/en-us/azure/api-management/api-management-revisions) separately illustrate controlled API changes. Neither is an Inframeld dependency or proof of implementation.
- [clig.dev](https://clig.dev/#arguments-and-flags) informs explicit risk acknowledgment and scriptable equivalents. Inframeld's backend owns the safety checks.
