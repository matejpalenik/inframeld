# Working configuration, direct queries and builds

Alice wants to try a new reranker before changing Production. She edits the Pipeline's working settings and queries that Pipeline directly. This development loop should be useful before a release build and should not create another execution service or a hidden publication path.

## Records and permissions

A Pipeline has one saved working configuration with immutable revision history. Save or restore creates a new current revision. Temporary overrides affect only that execution.

An execution-input snapshot captures exact effective settings, corpus and complete verified bindings. A PipelineVersion is successful release-build output. A reserved build identity is not yet serveable.

CLI `query --pipeline` uses Pipeline working settings. `query --deployment` uses Deployment serving selection. Humans and applications can receive explicit grants on either exact resource, but neither grant includes the other or its query-trace inspection permission. Captured provenance is not a new Experiment resource or a permission certificate.

## Follow the development loop

1. Capture working revision 17 and any explicit supported override. Freeze corpus selection before ordinary Indexing preparation.
2. Reuse verified data when compatible. Prompt/reranker changes can reuse materializations, while changed parsing, embeddings or corpus may need disclosed paid preparation. Pins, current access, health and limits still apply.
3. Execute the direct question through ordinary Pipeline behavior and ModelGateway. Concurrent edits do not change this admitted input.
4. Optionally evaluate fixed configurations with separately selected generator/judge bindings. Cases never supply reference answers or expected evidence to Pipeline execution. Choosing generator/judge connections does not change the Pipeline's settings.
5. Explicitly save the settings Alice wants. CLI Build captures current saved configuration and corpus, not unsaved overrides or an evaluation run ID. Show configuration/corpus/binding and sample/full-corpus mismatches as evidence limits, not a mandatory quality gate.

Finish is the default setup completion action. No generator, judge or evaluation is required for a useful first pipeline.

## Build and target selection

The CLI coordinator selects the sole live Deployment or requires a choice when there are several. Never fan out. With none, ordinary Build leaves an unpublished version. Existing first-publication onboarding retains its separate creation authority. No separate CLI apply command is required.

The underlying build takes caller-captured authorized configuration/corpus. Explicit CLI Build supplies current saved settings. Document-triggered work supplies the Deployment-selected configuration. The common build must not re-resolve current working settings.

Build verifies readiness but cannot move traffic alone. Manual mode leaves ready output, while Automatic coordinates separate conditional publication under captured/current permissions. A denied policy-controlled automatic workflow cannot silently downgrade to another behavior.

Edits, restores, direct queries and evaluation neither publish nor supersede pending publication. Development-only documents stay outside live-watched collections. Re-enabling Automatic reviews the currently serving version's configuration first, not a stale automatic binding. A different saved selection is explicit.

## Connections, portability and scope

Connection managers may make reviewed shared live changes without Build or per-Deployment release authority. Pipeline editors cannot infer that capability. A PipelineVersion selects connection IDs, not executable old access settings. Relevant access changes stop remaining dispatch. Rollback does not restore endpoints or secrets. A distinct connection selected on the working Pipeline supports an isolated migration.

Configuration export excludes Deployments and versions. Complete supported TOML definitions and protected Evaluation JSONL transfer have separate boundaries. Preserve explicit resource names, display labels and permanent IDs. Planned hook interfaces are not executable hooks.

## Show the state that actually changed

For change review, distinguish Current / Proposed intent, confirmed Before / Now effects and Reviewed / Now state changes since review.

A saved-revision delta does not change an already admitted build. Ready output is not a live-version delta. Keep unchanged build/live facts neutral and retain current-authority/revision guards. Follow [Pipeline change review](../../../../docs/development/pipelines-and-releases.md#change-review) and [shared CLI deltas](../../../../docs/development/api-contracts.md#cli-change-presentation) for exact presentation.

## Status and sources

The CLI development loop and exact-resource query permissions are accepted design. Public schema/route mapping, runtime qualification and delivered UI behavior must be checked separately. V1 uses a Rust CLI and independent Ory account UI. Full Studio is deferred.

- [Working configuration](../../../../docs/development/pipelines-and-releases.md#working-configuration), [direct queries](../../../../docs/development/pipelines-and-releases.md#preview), [query records](../../../../docs/development/data-model.md#query-execution-records), [Access query authority](../../../../docs/development/access-control.md#pipeline-query-authority) and [build/release behavior](../../../../docs/development/pipelines-and-releases.md).
- [Portability](../../../../docs/development/configuration-portability.md), [CLI delivery ownership](../../../../docs/development/cli-delivery-plan.md), [starter generation/review](../../../../docs/development/evaluation.md#generation) and the historical [CLI development-loop journey](https://github.com/matejpalenik/inframeld/issues/172).
- [ADR-0052](../../../../docs/adr/ADR-0052-separate-experimental-execution-from-release-ready-pipeline-builds.md) explains direct execution. [ADR-0055](../../../../docs/adr/ADR-0055-deliver-cli-first-v1-through-openapi-generated-clients.md) explains delivery. [ADR-0056](../../../../docs/adr/ADR-0056-support-explicit-local-hosted-or-disabled-reranking.md) selects explicit hosted reranking and local Ettin 32M while preserving bounded candidate identity.
