# Working configuration, direct queries and builds

<a id="records-and-permissions"></a>

## Choose a focused reading task

- For saved configuration changes, read [Working configuration](working-configuration.md).
- For temporary questions, read [Direct queries](direct-queries.md).
- For readiness builds, read [Build preparation](build-preparation.md).

## Records and permissions

A Pipeline has one saved working configuration with immutable revision history. Save or restore creates a new current revision. Temporary overrides affect only that execution.

An execution-input snapshot captures exact effective settings, corpus and complete verified bindings. A PipelineVersion is successful release-build output. A reserved build identity is not yet serveable.

CLI `query --pipeline` uses Pipeline working settings. `query --deployment` uses Deployment serving selection. Humans and applications can receive explicit grants on either exact resource, but neither grant includes the other or its query-trace inspection permission. Captured provenance is not a new Experiment resource or a permission certificate.

<a id="follow-the-development-loop"></a>

## Follow the development loop

1. Capture working revision 17 and any explicit supported override. Freeze corpus selection before ordinary Indexing preparation.
2. Reuse verified data when compatible. Prompt/reranker changes can reuse materializations, while changed parsing, embeddings or corpus may need disclosed paid preparation. Pins, current access, health and limits still apply.
3. Execute the direct question through ordinary Pipeline behavior and ModelGateway. Concurrent edits do not change this admitted input.
4. Optionally evaluate fixed configurations with separately selected generator/judge bindings. Cases never supply reference answers or expected evidence to Pipeline execution. Choosing generator/judge connections does not change the Pipeline's settings.
5. Explicitly save the settings Alice wants. CLI Build captures current saved configuration and corpus, not unsaved overrides or an evaluation run ID. Show configuration/corpus/binding and sample/full-corpus mismatches as evidence limits, not a mandatory quality gate.

Finish is the default setup completion action. No generator, judge or evaluation is required for a useful first pipeline.

<a id="connections-portability-and-scope"></a>

## Connections, portability and scope

Connection managers may make reviewed shared live changes without Build or per-Deployment release authority. Pipeline editors cannot infer that capability. A PipelineVersion selects connection IDs, not executable old access settings. Relevant access changes stop remaining dispatch. Rollback does not restore endpoints or secrets. A distinct connection selected on the working Pipeline supports an isolated migration.

Configuration export excludes Deployments and versions. Complete supported TOML definitions and protected Evaluation JSONL transfer have separate boundaries. Preserve explicit resource names, display labels and permanent IDs. Planned hook interfaces are not executable hooks.

<a id="separate-a-pipeline-from-a-deployment"></a>

<a id="model"></a>

<a id="1-separate-a-pipeline-from-a-deployment"></a>

## Separate a Pipeline from a Deployment

A **Pipeline** has one saved **working configuration**, the settings Alice is editing. Each save has an immutable revision. A direct query executes those current settings, with any explicit supported per-request overrides. The request records its exact effective configuration and corpus as **captured execution inputs** so later edits cannot change admitted work. This execution provenance is not an Experiment resource or a release version.

A **PipelineVersion** is the result of a successful release build: fixed settings with complete, verified bindings to the exact prepared indexes it needs. A **Deployment** is the stable target customers query, such as Production. It selects a ready PipelineVersion, never the working configuration or an execution-input snapshot. It does not deploy customer application code.

A Deployment stores references called **pointers**: current is live, candidate is being tried, and previous is the designated rollback target. Changing these references leaves the customer's endpoint unchanged.

<a id="review-evidence-and-expose-progress"></a>

<a id="review"></a>

<a id="7-review-evidence-and-expose-progress"></a>

## Review evidence and expose progress

The primary release workflow is inside Inframeld. Engineers review benchmark comparisons through the CLI or a future Studio view, and review observed canary behavior before explicitly requesting manual release transitions. These clients invoke the same application operations. Evaluation does not require a Studio-only workflow.

A higher score does not authorize promotion. Missing, failed, or regressed evidence needs explicit acknowledgment under the existing decision contract. Promotion still needs a usable version and a recorded operator decision.

Review may include a canary or an explicit zero-traffic review. V1 requires neither an arbitrary minimum observation period nor a statistical acceptance gate.

Evaluation uses embedded Ragas for optional starter generation and claim-based faithfulness under [ADR-0051](../../../../docs/adr/ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md). Generator and judge connections are selected explicitly. Neither changes the pipeline's generation model. A judge assesses claim support, not release eligibility. Accepted case revisions form the default regression benchmark. Comparisons execute both fixed inputs afresh, whether execution-input snapshots or ready versions. [Evaluation](../../inframeld-evaluation/references/generation-and-review.md) owns review, frozen inputs, passage coverage, scoring, and runtime qualification still required.

Optional automation calls the same commands with its own permissions and audit identity. No external CI service must own checks or approvals. [API contracts](../../inframeld-application-contracts/references/http-mcp-and-generated-clients.md) records the in-app workflow.

<a id="distinguish-explicit-decisions-from-work-that-runs-automatically"></a>

### Distinguish explicit decisions from work that runs automatically

| Mode | Explicit action | Work performed after admission |
| --- | --- | --- |
| **Manual releases** | Query, Evaluate, Build, Compare, attach/change a candidate, change its percentage, promote, reject, or roll back are explicit authorized operations. | Admitted work, progress tracking, safe retries, and cohort routing execute automatically. |
| **Automatic updates** | An authorized live-input source action or explicit Build requests preparation and conditional publication together. **Direct Pipeline queries and evaluation remain separate and explicit.** | The underlying build runs, followed by a separate publication attempt subject to its current guards. |

Once work is accepted and saved, the application carries it out. Neither mode requires a GitHub runner, webhook, callback, or general workflow engine.

<a id="maintainer-checks"></a>

<a id="8-maintainer-checks"></a>

## Maintainer checks

The following are acceptance conditions, not completed test results.

| Area | Required verification |
| --- | --- |
| **Working history and overrides** | Save/restore creates a new revision with expected-revision checks. Overrides change only the admitted query. Build never sources configuration from a run or unsaved editor state. |
| **Direct Pipeline queries and evaluation isolation** | Both work before any PipelineVersion exists when complete prepared inputs are available. No preparation/evaluation completion, save or restore changes live bindings or publication authority. |
| **Captured inputs** | Concurrent edits and source changes do not alter an admitted query or any evaluation case. Missing required preparation fails without incompatible-index or model fallback. |
| **Build selection and consent** | One Deployment resolves visibly, several require selection, none produces an unpublished version. Revisions or policy changing after review conflict. No fan-out or silent permission downgrade. |
| **Evaluation mismatch** | Report changed settings, corpus/sample or prepared bindings without requiring evaluation, silently reusing scores or asserting quality approval. |
| **Query retention and access** | Current access protects snapshots/results. Erasure defeats retention pins, trace opt-out is respected, and direct querying never enters production feedback counts. |
| **Initial creation** | The first real Deployment has a ready, same-project, compatible current version and an authorized decision, with no candidate, previous target, or rollout. The default route returns not-ready without generation beforehand. |
| **Deterministic routing** | Check fixed bucket examples, identity-scoped affinity, credential-rotation stability, increasing percentages, and pausing/resuming the same rollout. |
| **Missing affinity and project scope** | Reject missing application affinity while candidate traffic is enabled. Reject cross-project targets. |
| **Manual transitions** | Distinguish abort from rollback. Reject unavailable targets and stale revisions. Verify the one-step rollback rule and candidate guards. |
| **Mode switching** | Test both directions, including rejection of the mode-change request when a 0% candidate is still attached. Preserve the current version and retain the correct automatic-publication rollback target. |
| **Late or competing work** | Test rapid switching with late completion, overlapping uploads, publication-versus-switch races, lost acknowledgments, and lifecycle checks after deletion or rebinding. |
| **Permissions and in-flight requests** | Exercise permission changes and query completion across promotion without losing required retention protection or bypassing current access rules. |
| **Audit and feedback** | Record the actor, selected versions, rollout/revision, decision acknowledgment, and outcome. Preserve original receipt attribution for late feedback. Do not retain raw affinity values unnecessarily. |

These checks cover the routing and transition contract, including the additional publication-mode races.

<a id="status-and-sources"></a>

## Status and sources

The CLI development loop and exact-resource query permissions are accepted design. Public schema/route mapping, runtime qualification and delivered UI behavior must be checked separately. V1 uses a Rust CLI and independent Ory account UI. Full Studio is deferred.

- [Working configuration](working-configuration.md#working-configuration), [direct queries](direct-queries.md#preview), [query records](records.md#query-execution-records), [Access query authority](../../inframeld-access-models/references/query-and-document-authorization.md#pipeline-query-authority) and [build/release behavior](./configuration-queries-and-builds.md).
- [Portability](../../inframeld-application-contracts/references/configuration-export-and-import.md), [CLI delivery ownership](../../inframeld-architecture/references/v1-scope-and-extension-boundaries.md), [starter generation/review](../../inframeld-evaluation/references/generation-and-review.md#generation) and the historical [CLI development-loop journey](https://github.com/matejpalenik/inframeld/issues/172).
- [ADR-0052](../../../../docs/adr/ADR-0052-separate-experimental-execution-from-release-ready-pipeline-builds.md) explains direct execution. [ADR-0055](../../../../docs/adr/ADR-0055-deliver-cli-first-v1-through-openapi-generated-clients.md) explains delivery. [ADR-0056](../../../../docs/adr/ADR-0056-support-explicit-local-hosted-or-disabled-reranking.md) selects explicit hosted reranking and local Ettin 32M while preserving bounded candidate identity.
