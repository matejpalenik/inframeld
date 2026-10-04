# ADR-0052: Separate experimental execution from release-ready pipeline builds

**Status:** Accepted. Partially supersedes [ADR-0031](ADR-0031-compare-fresh-executions-against-frozen-benchmarks.md) on ready-version-only comparison inputs and [ADR-0047](ADR-0047-support-reversible-publication-modes-per-deployment.md) on the configuration-update interaction.

**Date:** 2026-09-29

**Terminology clarification, 2026-10-02:** The historical title and filename are retained. The selected capability is **Query on a Pipeline** using its current saved configuration, not an Experiment domain/resource or an Execute experiments permission. Query on a Deployment uses its selected ready version. Separately granted trace inspection targets the exact Pipeline or Deployment; both humans and applications may be eligible under current Access/source checks. Captured request/evaluation inputs are execution provenance, not another release version. References below to preview/experimental execution describe this same direct-query path, not another product concept. The original alternatives and rationale remain evidence of the earlier decision.

## Context and Problem Statement

Alice wants to try two rerankers while SupportBot continues querying Production. Requiring a release-ready PipelineVersion before every question or evaluation puts the release-build boundary too early. Executing changing settings without recording their exact inputs would instead make results impossible to explain.

We need a small development loop: edit, preview, evaluate, then deliberately build the pipeline's saved configuration when it is ready for release. The CLI must not require building from an evaluation run or a separate apply command. Experimentation must never inherit permission to publish merely because Production uses Automatic updates.

## Considered Options

- **Build a ready version for every experiment:** reuses the earlier execution contract, but requires release-version management during ordinary experimentation.
- **Add a second live Deployment for experiments:** provides another stable serving target, but still requires built versions and adds release lifecycle management that this loop does not need.
- **Execute frozen experimental inputs through a protected preview API:** keeps experimentation separate from release versions while sharing preparation, pipeline execution, access checks and ModelGateway with production.

These are design trade-offs, not measured performance or usability results.

## Decision Outcome

Choose the protected direct Pipeline query API. Each Pipeline has one saved working configuration with immutable revision history. Temporary overrides affect only the requested execution. Restoring old settings creates a new current revision. There is no Experiment resource or named-experiment/branching subsystem in v1.

Pipelines captures exact effective settings and corpus inputs for each direct query/evaluation before execution. Compatible prepared-data bindings are fixed before questions run. These captured inputs are execution provenance, not release-ready PipelineVersions, Deployments or separately managed Experiments. Preparation still verifies required indexes and may incur paid work. Direct querying is not another service, unrestricted provider proxy or weaker RAG implementation.

The user-facing `inframeld build` captures the current saved configuration and selected corpus, not a run ID or unsaved overrides. With one live Deployment it selects that target; with several it requires a choice, and scripts provide it explicitly. With none it creates an unpublished ready version. Existing first-publication onboarding retains its separately authorized creation path. Build never implicitly targets every Deployment.

For a selected Manual Deployment, Build leaves the new version ready for explicit release. For an Automatic Deployment, admission authorizes ordinary preparation followed by separate conditional publication to that exact target. Current permissions and publication guards still apply. There is no separate CLI apply command, and the underlying build operation remains readiness-only under [ADR-0033](ADR-0033-separate-build-readiness-from-release-authority.md).

Automatic document updates keep using the Deployment's explicitly selected configuration, never the Pipeline's changing working copy. Experimental inputs do not silently change live-watched collections. Editing, restoring, preparing, previewing and evaluating never authorize publication.

Comparisons may use experimental snapshots, ready versions, or one of each. Both sides execute freshly with identical frozen benchmark/evaluator revisions. Evaluation is optional; input differences from earlier evaluation must be disclosed, not treated as approval or an automatic build rejection.

[Pipelines and Releases](../development/pipelines-and-releases.md#working-configuration) owns the lifecycle. [Evaluation](../development/evaluation.md#comparison) owns comparison evidence. [The data model](../development/data-model.md#experimental-execution-records) owns logical records, and [CLI development loop](https://github.com/matejpalenik/inframeld/issues/172) illustrates the interaction.

[ADR-0054](ADR-0054-use-shared-current-model-connections.md) clarifies the boundary of frozen inputs: Pipeline settings, model choices, corpus and prepared bindings remain fixed, while selected connections are shared current operational dependencies. Admitted work observes access revisions and stops remaining model dispatches after relevant changes rather than using historical access settings. Preview itself never edits a connection. Shared connection administration may affect production in either publication mode; Pipeline rollback does not restore it.

## Consequences

- Engineers can test configurations before committing them to release versions, while concurrent edits cannot change an admitted run.
- Changes to chunking, embedding or corpus can require substantial preparation even without a release build. Compatible artifacts are reused, not mutated in place.
- Query and trace-inspection authority are separately scoped to the exact Pipeline or Deployment. A Deployment Query grant does not authorize direct Pipeline querying; Pipeline Query does not grant diagnostic inspection, Build or publication. Bounded work, current source access, erasure and protected history remain required. [Access](../development/access-control.md#pipeline-query-authority) owns these accepted scopes and pending implementation mappings.
- A reviewed configuration can change before Build. Admission must bind the reviewed revisions, report conflicts, and disclose any evaluation mismatch. It cannot silently build a different latest configuration.
- No new service, workflow engine, schema migration, API implementation or executed test follows from this document. Concrete action/HTTP mappings, resource bounds and runtime qualification remain implementation obligations.

## Links

- [ADR-0031](ADR-0031-compare-fresh-executions-against-frozen-benchmarks.md) retains fresh comparisons; only its ready-version-only restriction is superseded.
- [ADR-0047](ADR-0047-support-reversible-publication-modes-per-deployment.md) retains reversible modes, authorized source updates and publication guards. Build replaces the earlier configuration Save and apply interaction.
- [ADR-0040](ADR-0040-bind-pipeline-versions-to-verified-profile-specific-materializations.md) retains verified index readiness; [ADR-0051](ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md) retains Ragas and its qualification requirements.
- [Google Dialogflow versions and environments](https://docs.cloud.google.com/dialogflow/cx/docs/concept/version) is an external precedent for testing drafts before production versions, not an Inframeld dependency or proof of our implementation.
- [clig.dev](https://clig.dev/#interactivity) informs explicit consequences and noninteractive operation. Terminal examples are proposed contracts, not implemented commands.
