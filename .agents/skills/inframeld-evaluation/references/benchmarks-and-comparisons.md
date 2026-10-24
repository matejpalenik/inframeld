# Freeze inputs and compare fresh executions

Alice starts a comparison, then edits a case reference and the Pipeline's working settings. The admitted run must still answer its original questions with its captured configuration. It cannot quietly become a different experiment halfway through the cases.

## What is frozen

A benchmark fixes exact case revisions and membership. An evaluator revision fixes scoring configuration. Execution inputs capture effective working settings/overrides, exact corpus, selected baseline and complete verified bindings.

Either comparison side may be a ready PipelineVersion or a captured working-configuration input. No new release build is required merely to compare them.

## Follow a comparison

1. Admit both selected sides against one frozen benchmark and evaluator. Capture settings and baseline selection once, not per case.
2. Observe current access revisions for every generator, Pipeline and judge connection. Historical observations do not authorize executing old settings.
3. Perform ordinary preparation through Indexing and ModelGateway. Preparation may cost money but creates no release authority.
4. Execute each question through ordinary Pipeline behavior without reference answers or expected evidence. Score final supplied context under the evaluator contract.
5. Retain partial results and finalize with the selected consistency checks. Show paired coverage, failures, exclusions and interrupted/changed-environment state.

Both sides execute freshly. Reusing a retained input snapshot means another execution, never reuse of its old scores. Historical OpenEvals observations retain their original meaning. Matching model aliases alone cannot prove that behavior stayed unchanged.

## Changed inputs and current access

A relevant connection-access change stops subsequent dispatch rather than mixing environments, executing old settings or rebinding the run. Record actual access/credential observations for calls already made. Key-only rotation or metadata rename does not itself interrupt.

A fresh comparison needs new admission of both sides. Historical Pipeline execution still uses current connectivity.

An unavailable execution dependency may stop execution. An absent passage-coordinate mapping instead makes that metric unscorable.

Keep admitted case membership fixed without leaking protected counts or silently substituting a newer source or reduced benchmark. Frozen inputs do not freeze permissions, suspension or erasure.

Temporary evaluation overrides do not save the Pipeline. Alice explicitly saves desired settings before Build captures current saved configuration. Report configuration/corpus/binding and sample-versus-full-corpus mismatches as limits of evidence, not an implicit quality gate.

## Status and sources

These are accepted comparison and consistency rules. Runtime integration, exact schemas, performance and judge calibration still require their stated evidence. Scores do not authorize releases or pause Automatic updates. Manual release mode controls serving pointers, while shared connection administration can still change live connectivity.

- [Frozen execution](../../../../docs/development/evaluation.md#comparison), [comparison/history](../../../../docs/development/evaluation.md#history), [working-configuration loop](../../../../docs/development/pipelines-and-releases.md#preview), [execution records](../../../../docs/development/data-model.md#query-execution-records) and [dispatch freshness](../../../../docs/development/model-connections.md#dispatch-freshness).
- [ADR-0031](../../../../docs/adr/ADR-0031-compare-fresh-executions-against-frozen-benchmarks.md), [ADR-0052](../../../../docs/adr/ADR-0052-separate-experimental-execution-from-release-ready-pipeline-builds.md) and [ADR-0054](../../../../docs/adr/ADR-0054-use-shared-current-model-connections.md).
