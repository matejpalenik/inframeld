---
name: inframeld-pipelines-releases
description: Explain or review Inframeld pipeline builds, serving, feedback, canaries, rollback and reversible automatic/manual publication. Use for the in-app RAG lifecycle and default onboarding, not a GitHub CI workflow.
---

# Inframeld Pipelines and Releases

Explain one user workflow while keeping two owners clear. Pipelines owns immutable configuration, builds, query orchestration, receipts, and feedback. Releases owns Deployment serving pointers, cohorts, publication modes, and transitions.

## Scope and reading route

Default to read-only explanation and review. Loading this skill does not authorize code edits, releases, or external mutations. Read the relevant current section, identify its status, and report contradictions.

- [Pipelines and Releases](../../../docs/development/pipelines-and-releases.md) owns builds, serving, modes, and transition examples. Read [Pipeline records](../../../docs/development/data-model.md#pipelines) and [Release records](../../../docs/development/data-model.md#releases) for definitions.
- [Answer feedback](../../../docs/development/answer-feedback.md) owns receipt ratings and reporting. [Onboarding](../../../docs/development/onboarding.md) owns private defaults and first publication.
- Decisions: [immutable lineage](../../../docs/adr/ADR-0008-preserve-immutable-versions-and-their-provenance.md), [ready bindings](../../../docs/adr/ADR-0040-bind-pipeline-versions-to-verified-profile-specific-materializations.md), [canary assignment](../../../docs/adr/ADR-0032-keep-canary-assignment-stable-for-the-same-caller-and-affinity-key.md), [separate release authority](../../../docs/adr/ADR-0033-separate-build-readiness-from-release-authority.md), [publication modes](../../../docs/adr/ADR-0047-support-reversible-publication-modes-per-deployment.md), and [feedback](../../../docs/adr/ADR-0043-keep-one-current-feedback-rating-per-answer-and-originating-principal.md).
- Read [Access control](../../../docs/development/access-control.md) for Manage releases and creation checks; [Jobs](../../../docs/development/jobs-and-idempotency.md), [Indexing](../../../docs/development/indexing.md), and [Evaluation](../../../docs/development/evaluation.md) only when needed.
- [Maintainer checks](../../../docs/development/pipelines-and-releases.md#maintainer-checks) summarize release transitions and races.

- For stale work, follow [publication modes and guards](../../../docs/development/pipelines-and-releases.md#modes). For late ratings, follow [receipt attribution](../../../docs/development/answer-feedback.md#lifecycle) and [reporting](../../../docs/development/answer-feedback.md#reporting).

## Essential boundaries

A Pipeline is the logical configuration/test association. A PipelineVersion freezes configuration and complete prepared bindings. A reserved build identity is not yet serveable. A Deployment is the stable serving identity with current, candidate, and previous targets. An AnswerReceipt records what served; feedback is its current rating. Do not infer an ORM class per concept or load all receipts through a giant Pipeline aggregate.

Build publishes complete ready bindings after Indexing verification; it never moves traffic alone. Queries select one version with a bounded retention pin and keep that attribution throughout execution. Current authorization and health are checked before egress and disclosure. Mid-query releases do not silently reroute work. ModelGateway handles embeddings and generation. Failed required shards, credentials, or reranking do not justify a different provider or unfiltered fallback.

Canary affinity controls cohorts, not identity or permissions. Stable principal and rollout identities participate in assignment; rotating a key or changing percentage must not reshuffle callers. Ten percent is a share of identities, not an exact request count. Aborting B preserves current A and previous Z; promoting B makes A previous. Rollback consumes its one-step target and is blocked by an attached candidate or unusable target. Do not choose another target silently.

Manage releases is one action per Deployment covering publication, candidate/canary control, rollback, mode switches, and automatic input selection. It replaces earlier Publish/deploy wording. Delete, Build, document access, and non-serving Edit configuration remain separate. Human creation uses project Create Deployment and atomically records the ready initial version, Deployment, and explicit creator grants. Creator history never overrides later grant removal.

Private starter provisioning explicitly records the creator as both ordinary member and manager of its group under the [Access rule](../../../docs/development/access-control.md#group-managers). This does not replace separate build or release grants.

The default path starts Automatic updates; explicit new deployments default Manual releases with an automatic option. Mode belongs to the Deployment, not every deployment of a Pipeline. Before first publication, the default binding holds its mode/control revision and remains not-ready; no fake version is created. First publication transfers this state atomically.

Automatic updates uses complete authorized batches or explicit Save and apply actions, then normal Build and separate conditional publication. Require mutation/input rights, Pipeline Build, and target Manage releases; before the default Deployment exists, the authorized human instead needs project Create Deployment. Recheck current authority before dispatch and publication. A competing creation cannot authorize an update to someone else’s existing target. Failure keeps healthy current.

Automatic → manual invalidates pending publication while allowing useful builds to finish. Manual → automatic freezes selected inputs and admits fresh work; even a 0% attached candidate blocks the switch. Every switch advances the control revision, so off/on cannot revive an old job. Newest authorized request identity and current attempt/serving state guard publication. Superseded work cannot become a fallback after a newer failure. Canaries and rollback require manual mode; scores and feedback never authorize releases.

Receipts retain exact attribution and every final source, including uncited evidence. Lost-answer replay is receipt-only, not regeneration. Feedback permits one current editable rating per answer/originating principal, with current access, revisions, and retention. Late feedback stays on the original version/cohort. Coverage uses eligible produced receipts in the same authorized answer-time window; missing ratings are not negative votes and an application is not a verified human audience.

## Explain and review

Trace P12 → built P13 → comparison → canary → abort, then promotion and rollback separately. Include a late rating and an old automatic build finishing after off/on. Explain which current check prevents unwanted publication. Shared default selector shapes and HTTP/SDK/MCP concurrency remain qualification work. Do not invent a release engine, external runner, or parallel quickstart implementation.
