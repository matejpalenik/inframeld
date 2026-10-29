# Freeze inputs and compare fresh executions

<a id="freeze-inputs-and-compare-fresh-executions"></a>

Alice starts a comparison, then edits a case reference and the Pipeline's working settings. The admitted run must still answer its original questions with its captured configuration. It cannot quietly become a different experiment halfway through the cases.

<a id="what-is-frozen"></a>

## Apply accepted PD-EVALUATION-02

Accepted [PD-EVALUATION-02](decision-run-and-result-contracts.md#approved-resolution) selects this workflow's detailed contract. A run can answer successfully while a metric cannot be calculated. A comparison can also have missing pairs. Those facts must remain visible instead of collapsing into one success flag or score. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## What is frozen

A benchmark fixes exact case revisions and membership. An evaluator revision fixes scoring configuration. Execution inputs capture effective working settings/overrides, exact corpus, selected baseline and complete verified bindings.

Either comparison side may be a ready PipelineVersion or a captured working-configuration input. No new release build is required merely to compare them.

<a id="follow-a-comparison"></a>

## Follow a comparison

1. Admit both selected sides against one frozen benchmark and evaluator. Capture settings and baseline selection once, not per case.
2. Observe current access revisions for every generator, Pipeline and judge connection. Historical observations do not authorize executing old settings.
3. Perform ordinary preparation through Indexing and ModelGateway. Preparation may cost money but creates no release authority.
4. Execute each question through ordinary Pipeline behavior without reference answers or expected evidence. Score final supplied context under the evaluator contract.
5. Retain partial results and finalize with the selected consistency checks. Show paired coverage, failures, exclusions and interrupted/changed-environment state.

Both sides execute freshly. Reusing a retained input snapshot means another execution, never reuse of its old scores. Historical OpenEvals observations retain their original meaning. Matching model aliases alone cannot prove that behavior stayed unchanged.

<a id="changed-inputs-and-current-access"></a>

## Changed inputs and current access

A relevant connection-access change stops subsequent dispatch rather than mixing environments, executing old settings or rebinding the run. Record actual access/credential observations for calls already made. Key-only rotation or metadata rename does not itself interrupt.

A fresh comparison needs new admission of both sides. Historical Pipeline execution still uses current connectivity.

An unavailable execution dependency may stop execution. An absent passage-coordinate mapping instead makes that metric unscorable.

Keep admitted case membership fixed without leaking protected counts or silently substituting a newer source or reduced benchmark. Frozen inputs do not freeze permissions, suspension or erasure.

Temporary evaluation overrides do not save the Pipeline. Alice explicitly saves desired settings before Build captures current saved configuration. Report configuration/corpus/binding and sample-versus-full-corpus mismatches as limits of evidence, not an implicit quality gate.

<a id="freeze-inputs-and-execute-explicitly"></a>

<a id="comparison"></a>

<a id="3-freeze-inputs-and-execute-explicitly"></a>

## Freeze inputs and execute explicitly

A **benchmark revision** fixes an ordered set of case revisions. An **evaluator revision** fixes metric definitions, prompts, library, judge, and settings. **Admission** means validating and saving the operation before a durable worker starts it.

1. Select a ready PipelineVersion or explicit direct Pipeline query execution of the working configuration, optionally with bounded temporary overrides. A retained execution-input snapshot may also supply exact comparison inputs while its dependencies remain available. Select accepted cases or an existing benchmark. With no eligible cases, explain why and create no paid run.
2. Select the judge explicitly, offering an existing connection. Show review coverage, configuration revision/overrides or version, corpus scope, required preparation, metrics, outgoing data, cost availability, and budget. Freeze effective execution inputs, benchmark/evaluator revisions and effective access conditions at admission. A later edit cannot change them.
3. For newly captured working-configuration inputs, resolve complete verified bindings through [ordinary direct-query preparation](../../inframeld-pipelines/references/direct-queries.md#preview). For a ready version or retained execution-input snapshot, verify its recorded bindings are still available. Do not rebuild or replace missing historical bindings to make that input runnable. Then execute each question through the same pipeline behavior as live queries: query embedding, permission-filtered retrieval, configured reranking, final context assembly, and generation. **Do not send the reference answer or expected passage to the pipeline.** That would leak the answer into the system being tested. No question runs against incomplete or incompatible indexes.
4. Capture permitted evidence at each measured stage and the exact final context sent to generation. Calculate deterministic passage/citation signals, then judge eligible answers with Ragas faithfulness.
5. Save per-case outcomes and summaries including incomplete and failed cases. Generation, review, save, and build actions never silently start this run.

A run executes one exact version or execution-input snapshot for all its cases. A comparison executes **both baseline and candidate freshly** under identical frozen benchmark and evaluator revisions. Here candidate means the proposed comparison input, not necessarily a release candidate attached to a Deployment.

| Comparison inputs | Meaning |
| --- | --- |
| **Two execution-input snapshots** | Try two configurations, such as reranker A versus B, without creating a release-ready PipelineVersion. |
| **Ready version and execution-input snapshot** | Compare a fixed released/built baseline with the proposed working settings. Resolve a live baseline to its exact version before admission, not separately for each case. |
| **Two ready versions** | Preserve the existing post-build comparison workflow. |

For example, evaluation A captures working revision 17 with reranker A. Alice then saves revision 18 with reranker B. A continues using its original inputs. A new comparison may reference both snapshots but must execute both sides again. It does not subtract their old scores. Reuse compatible ready materializations, not historical answers or a newer corpus substituted behind a selected input. Revoked access or lost dependencies remain failures/unavailability, even for a retained snapshot.

Working-configuration evaluation records its effective overrides without saving them into the Pipeline. To ship the change, Alice explicitly saves the desired settings, then invokes Build on the Pipeline's current saved configuration. Build is not sourced from this run. Its review shows any mismatch in configuration, corpus or prepared inputs, including a sample evaluation versus full-corpus build. Matching input identity is not an automatic quality approval, and a mismatch does not create a compulsory judge call. [Pipelines](../../inframeld-pipelines/references/build-preparation.md#build) owns that boundary.

The existing [durable jobs](../../inframeld-application-contracts/references/jobs-and-recovery.md) own continuation, attempts, cancellation, and uncertainty. Closing a watcher does not repeat or cancel work. Reopening by operation/job ID finds saved progress. Checkpoint bounded preparation units and cases. Do not keep a database transaction open during a model call.

<a id="input-reliability"></a>

<a id="keep-the-tested-inputs-fixed-not-the-callers-permissions"></a>

### Keep the tested inputs fixed, not the caller's permissions

Alice starts a run on `contracts` with saved configuration 17, 12 exact document versions, 20 already accepted case revisions and her explicitly selected `quality-judge` connection. These are illustrative values, not defaults or a promise that generation yields 20 accepted cases. The admission review also discloses preparation, outgoing data, cost availability and budget. If reviewed inputs change before admission, report the conflict instead of silently accepting newer state.

After admission, a teammate saves configuration 18, uploads a newer contract and edits a case's reference answer. The admitted run still identifies configuration 17, its original corpus and the original case revision. An edit creates an unreviewed revision for future review. A newly assembled default benchmark excludes that case until its new revision is accepted. An existing frozen benchmark is not rewritten or silently replaced.

For the question "How long is the cancellation period?", the case may store the reference answer "30 days" and the expected cancellation clause in contract v3. The Pipeline receives the question through its normal execution contract, not either of those evaluation-only fields. Its retrieval must find evidence normally. Passage scoring consumes the expectation separately. Faithfulness uses the actual answer and only the final context sent to generation, never the reference answer or unused expected text as extra support.

| Change or missing input | Required behavior |
| --- | --- |
| Saved configuration, current case content or document latest-version pointer changes after admission | Keep the exact captured execution inputs and case revisions. Do not follow mutable pointers between cases. |
| A required historical execution binding or index is unavailable | Do not execute against incomplete dependencies, rebuild missing historical bindings or substitute a newer corpus. Report the blocked/failed work through existing run/job outcomes and preserve permitted saved results. Newly captured working inputs may still use their separately admitted ordinary preparation. |
| Execution dependencies are ready, but an expected passage lacks a verified source mapping | Mark the affected passage metric unscorable with its reason. This is not an ordinary retrieval miss or permission to declare other metrics successful. Each metric keeps its own eligibility checks. |
| Source access is revoked or evidence erased | Stop prohibited work and protect questions, references, answers, evidence, identifiers and aggregates. An old snapshot grants no continuing access. Do not reconstruct erased content. |
| A selected connection's access revision changes | Apply [connection consistency](gateway-and-jobs.md#connection-consistency): stop further dispatch, retain actual observations and identify interrupted/changed-environment results. Do not use old connectivity or silently switch the remaining cases to new settings. Credential-only rotation and metadata-only rename retain their existing exceptions. |

Never silently remove a requested case because its evidence is unavailable. Preserve the admitted selection and unavailable outcomes under current access and retention, not an always-public count of that selection. A deliberate smaller selection is a new explicit admission, not a repair to the meaning of the old run. A fresh comparison executes both sides against the same frozen benchmark/evaluator and reports missing pairs rather than reusing earlier scores.

These rules use the existing execution framework. Accepted PD-EVALUATION-01/02 and PD-INDEXING-03 select exact logical inputs, source-coordinate proof, failure outcomes and protected saved-result disclosure. Native implementation and evidence remain required.

Implementation is divided into execution, scoring, comparison, protected history and CLI results. Evaluation qualification and the CLI qualification tickets must test the resulting behavior. This example defines no endpoint, permission identifier or physical table. [Evaluation records](records.md#evaluation) describes the logical relationships.

<a id="compare-compatible-observations-showing-missing-pairs"></a>

### Compare compatible observations, showing missing pairs

Calculate paired changes only where both sides were successfully scored under compatible conditions. Show full admitted counts, each side's failures/exclusions, and paired count. Never claim improvement by discarding failed candidate cases.

| Comparison | Treatment |
| --- | --- |
| Same corpus, changed configuration | Same benchmark/evaluator and effective document scope. Identify changed settings. |
| Changed chunking with preserved coordinates | Passage coverage remains comparable despite different chunk IDs. |
| Deliberate corpus/parser change | Label it. Unavailable expected versions or unproved mappings are unscorable. Never retarget expectations silently. |
| Changed questions, metric definitions, or incompatible access | No like-for-like improvement claim. Choose compatible inputs and rerun both sides. |
| Working-configuration sample compared with full-corpus behavior | Label the scope difference. Neither a successful sample nor matching model names validates an unevaluated full-corpus build. |
| Historical OpenEvals score | Retain its original evaluator identity. Never relabel boolean groundedness as Ragas faithfulness or calculate cross-definition improvement. |

Library, prompt/schema, model binding/settings, or metric changes produce a new evaluator revision. Both fresh runs use it. A matching remote alias does not prove unchanged provider behavior. Record observed identity and disclose this limitation. Broad-access engineer results do not establish what a restricted bot will see.

<a id="keep-evidence-separate-from-release-authority"></a>

<a id="release"></a>

<a id="10-keep-evidence-separate-from-release-authority"></a>

## Keep evidence separate from release authority

Evaluation is evidence, not permission to publish. Saving cases, completing a run, or receiving a webhook changes neither publication mode nor serving pointers.

In **Manual releases**, an authorized person/application explicitly requests release. Readiness, expected deployment revision, permissions, and duplicate-request checks still apply. Record the evaluation reference and acknowledgment of missing or regressed evidence where required by the release workflow.

In **Automatic updates**, an authorized live-input source operation or explicit policy-controlled Build supplies authority independently of evaluation. Saving working configuration or completing direct-query preparation supplies none. A comparison neither pauses updates nor starts a hidden judge. Use Manual releases when the live version selection must remain fixed during review. This does not freeze shared connectivity. See [Pipelines and Releases](../../inframeld-releases/references/publication-and-automatic-updates.md#modes) and [connection consistency](gateway-and-jobs.md#connection-consistency).

<a id="keep-evaluation-contracts-application-owned"></a>

### Keep evaluation contracts application-owned

For example, the CLI accepts one generated case revision, then separately requests an evaluation of a frozen benchmark. These are distinct application operations. Accepting a draft must not start paid evaluation. [Evaluation](generation-and-review.md) defines generation, revision-specific review, benchmark freezing, durable execution, and current-access history inspection for every client, including a future Studio view.

Contracts must expose immutable revision identities, review states, explicit model connection references, per-metric definitions/statuses/denominators, partial outcomes, and recoverable job identity. Evaluation input distinguishes a ready PipelineVersion from a frozen execution-input snapshot, rather than requiring a release build or accepting mutable latest inputs. They must distinguish passage misses from unavailable source mappings and judge failures from low faithfulness. Do not expose Ragas configuration objects, provider credentials, or vendor result types as public application models. Do not reinterpret historical metric definitions.

Exact routes/request schemas and case-audience administration remain implementation design work. The [six exact-Pipeline use identifiers](../../inframeld-access-models/references/actions-and-initial-grants.md#reviewed-capability-catalogue) are accepted. CLI mockups are not implemented endpoints or permission names. This documentation change generates no contract artifact and adds no MCP tools. Future contract tests must cover these product behaviors through ordinary HTTP/application boundaries, without duplicating evaluation logic in clients.

<a id="status-and-sources"></a>

## Status and sources

These are accepted comparison and consistency rules. Runtime integration, exact schemas, performance and judge calibration still require their stated evidence. Scores do not authorize releases or pause Automatic updates. Manual release mode controls serving pointers, while shared connection administration can still change live connectivity.

- [Frozen execution](#comparison), [comparison/history](history-and-dataset-transfer.md#history), [working-configuration loop](../../inframeld-pipelines/references/direct-queries.md#preview), [execution records](../../inframeld-pipelines/references/records.md#query-execution-records) and [dispatch freshness](../../inframeld-application-contracts/references/model-dispatch-and-destinations.md#dispatch-freshness).
- [ADR-0031](../../../../docs/adr/ADR-0031-compare-fresh-executions-against-frozen-benchmarks.md), [ADR-0052](../../../../docs/adr/ADR-0052-separate-experimental-execution-from-release-ready-pipeline-builds.md) and [ADR-0054](../../../../docs/adr/ADR-0054-use-shared-current-model-connections.md).
