# Integrate Ragas through the existing gateway and jobs

<a id="integrate-ragas-through-the-existing-gateway-and-jobs"></a>

Alice starts generation and cancels while Ragas is still preparing its executor. Cancellation must reach those nested calls too. Checking only the final judge call would leave preparation free to spend money or send data outside Inframeld's normal controls.

<a id="roles-and-adapters"></a>

## Apply accepted PD-EVALUATION-03

Accepted [PD-EVALUATION-03](decision-ragas-integration-and-calibration.md#approved-resolution) selects this workflow's detailed contract. A judging model can produce valid JSON and still miss an unsupported claim. A narrow adapter and explicit human-labelled checks make the limits inspectable. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## Roles and adapters

Generator and judge bindings explicitly select authorized saved connections and model settings. They may reuse a key through an existing connection, but do not modify Pipeline generation settings. Ragas supplies algorithms, not case management, authorization, durable scheduling or another workflow engine.

Infrastructure adapters explicitly inherit the selected Ragas interfaces and convert vendor types locally. Public application records remain Inframeld-owned. Domain/application contracts must not import vendor schemas, SDK clients or credentials. Inspected v0.4.3 interfaces establish source compatibility only, not an executed integration.

<a id="follow-all-paid-work"></a>

## Follow all paid work

1. Admit bounded work through existing durable jobs and current operation authority. Observe every relevant connection-access revision.
2. Route extraction, synthesis, preparation, final judging, repairs and optional future embeddings through ModelGateway. No default provider clients, implicit model fallback or independent credentials are allowed.
3. Apply gateway limits and retry decisions to nested calls. Cancellation covers preparation before a library executor is returned.
4. Preserve checkpoints and partial results. A lost response or cancellation request is not proof that a dispatched call stopped or incurred no charge.
5. Stop later dispatch after relevant access changes and perform final consistency checks. Recovery follows the existing attempt/uncertainty protocol rather than unbounded regeneration.

Disable Ragas analytics and exporters and verify network behavior. This does not disable independently controlled Inframeld tracing. Additional judging/generation presets and external exporters remain deferred.

<a id="failure-and-qualification"></a>

## Failure and qualification

No reference answer or expected evidence enters Pipeline execution. All protected egress and later disclosure retain current access checks. Budget, cancellation, uncertain paid outcomes and library preparation need behavioral qualification, not merely signature-compatible adapters.

This reference owns routing, limits, failure, network and human-calibration qualification plans. No new MCP tools, runner, public schema or SDK-distribution choice follows from adopting Ragas.

- [Gateway adapters and pinned source evidence](#gateway), [Evaluation qualification](#qualification), [Model connections](../../inframeld-application-contracts/references/model-gateway-and-connections.md), [Jobs](../../inframeld-application-contracts/references/jobs-and-recovery.md) and [maintainer checks](metrics-and-evidence.md#maintainer-checks).
- [ADR-0051](../../../../docs/adr/ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md) and [V1 scope](../../inframeld-architecture/references/v1-scope-and-extension-boundaries.md) preserve application ownership and remaining qualification.

<a id="bind-ragas-to-modelgateway"></a>

<a id="gateway"></a>

<a id="6-bind-ragas-to-modelgateway"></a>

## Bind Ragas to ModelGateway

<a id="model-selection"></a>

<a id="select-existing-connections-for-separate-roles"></a>

### Select existing connections for separate roles

Starter generation and evaluation judging have separate explicitly selected bindings. Offer reuse of the pipeline's generation connection or another authorized saved connection without another key. Reuse is not implicit fallback. Generator and judge may share a connection. Disclose that using the same model to generate and judge is not independent assessment.

These choices do not change pipeline generation, embedding, or reranking settings. No provider or model family is mandatory. Chat success does not prove support for the schemas, context size, and limits needed here. [Optional preflight](../../../../docs/adr/ADR-0050-make-model-preflight-optional-and-record-runtime-validation.md) stays optional. Real work must still validate responses and report unsupported capabilities.

```text
Evaluation application service
  -> Ragas infrastructure adapter
     -> ModelGateway
        -> embedded LiteLLM
           -> selected authorized model

Includes extraction, synthesis, judging, permitted repairs,
and explicitly enabled future embeddings.
Pipeline execution retains its normal gateway path.
```

The service owns admission, authorization, snapshots, durable work, and results through application-owned protocols. Bootstrap constructs adapters. Domain/application contracts import no Ragas, LangChain, SDK, or vendor schema types. Adapters explicitly inherit their selected library interfaces. Application protocol implementations also follow repository inheritance/override conventions.

| Adapter | Responsibilities |
| --- | --- |
| **Structured LLM** | Explicitly inherit `InstructorBaseRagasLLM`. Implement `generate(prompt, response_model)` and asynchronous `agenerate(prompt, response_model)`. Convert library response models into application-owned gateway structured-output requests. Validate responses and reconstruct the required library type. Set `is_async = True` on the asynchronous adapter because the inspected prompt path reads it. |
| **Embedding** | Explicitly inherit `BaseRagasEmbedding`. Implement `embed_text` and asynchronous `aembed_text`, with bounded batches where required and the async capability signal used by consuming extractors. Route actual calls through an explicitly selected gateway binding. The starter preset authorizes none. |
| **Execution binding** | Fix selected connection IDs, model choices/settings, operation identity, deadline and budget. Observe current access revisions at admission and require them still current before each relevant dispatch. Never select a historical access configuration. Gateway resolves the current authorized credential. Ragas receives neither the key nor its store. |
| **Boundary conversion** | Convert errors/results into named application outcomes. Keep vendor-specific types, schemas, and compatibility shims in infrastructure. |

Workers use asynchronous calls. Any exposed synchronous path must use the same gateway and must not block the event loop or create another provider client. Qualify the actual bridge against the gateway contract. Do not assume a nested event loop is safe.

<a id="source-inspected-compatibility-not-a-tested-integration"></a>

### Source-inspected compatibility, not a tested integration

Evidence below is from **v0.4.3**, inspected on 2026-09-29. Lock and test the whole dependency set. Rolling documentation may use different API shapes.

| Source | Integration consequence |
| --- | --- |
| [LLM interfaces](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/llms/base.py), [structured prompts](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/prompt/pydantic_prompt.py) | Modern typed generation supports a custom adapter path. Prompt code also checks async capability. Method names alone are insufficient. |
| [Embedding interfaces](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/embeddings/base.py), [embedding extractor](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/testset/transforms/extractors/embeddings.py) | Modern and legacy APIs coexist. Verify the selected adapter against each consuming component. |
| [Metric base](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/collections/base.py), [Faithfulness](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/collections/faithfulness/metric.py) | The collection metric validates its LLM interface and uses it for extraction and support judgments. Capture intermediate results deliberately. Handle missing claims/evidence explicitly. |
| [Generator](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/testset/synthesizers/generate.py), [single-hop strategy](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/testset/synthesizers/single_hop/specific.py), [sample construction](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/testset/synthesizers/single_hop/base.py) | Older annotations coexist with modern prompt support. Retain scenario/source identity outside returned text. The executor handle does not cover all earlier preparation. |
| [Synthesizer defaults](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/testset/synthesizers/base.py), [extractor defaults](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/testset/transforms/base.py), [default transforms](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/testset/transforms/default.py) | Defaults can construct provider clients or add embedding/graph work. A top-level custom LLM does not automatically bind every nested component. |

Explicitly bind every extractor, synthesizer, metric, prompt/repair path, and persona-generation path if later enabled. Give Ragas no provider credentials, independent provider/LiteLLM clients, or endpoints. Missing bindings must fail, not invoke default factories. No capability failure may silently select another model.

<a id="keep-one-security-retry-and-telemetry-boundary"></a>

### Keep one security, retry, and telemetry boundary

<a id="connection-consistency"></a>

<a id="observe-shared-connectivity-without-weakening-frozen-comparisons"></a>

#### Observe shared connectivity without weakening frozen comparisons

Alice admits a comparison whose two sides use `company-gateway` access revision 7. A connection manager then activates revision 8. New work uses revision 8. The admitted comparison cannot keep calling revision 7 or silently finish the remaining cases under revision 8. Stop remaining model dispatches, preserve completed case outcomes with actual revision attribution and report an interrupted/incomplete comparison. Do not present its partial aggregate as a completed like-for-like improvement claim. To compare under revision 8, explicitly admit both sides freshly again, with normal cost review.

Capture the current access revision for every generator, pipeline and judge connection needed by the operation. Check it during preparation and before nested extraction, synthesis, judging and repair dispatches, including concurrent cases. Apply the same rule to reused historical snapshots and ready versions. Their definitions select connection identities and model settings, not old access revisions. An already-dispatched call may finish and incur cost. Its result remains attributed to that revision, and uncertain outcomes cannot be automatically repeated.

At result finalization, check for relevant access changes since admission. If detected, retain the actually completed observations but label the run/comparison interrupted or changed-environment, not complete unchanged-environment evidence. The existing job outcomes apply: a known precondition failure is failed. An uncertain paid outcome needs recovery. A later update after a successfully finalized run does not rewrite its historical completion or scores, but future comparisons must disclose the changed environment. Credential-only rotation and metadata rename do not alone interrupt a run. Record the credential revision actually used on each call.

This preserves frozen benchmark/evaluator and Pipeline inputs without granting historical connectivity. It also means Manual release mode freezes serving-version selection, not shared connection settings. [Model connections](../../inframeld-application-contracts/references/model-dispatch-and-destinations.md#dispatch-freshness) owns dispatch and [ADR-0054](../../../../docs/adr/ADR-0054-use-shared-current-model-connections.md) owns the architectural change. No new configuration branch, job engine or Ragas client is introduced.

ModelGateway retains authorization, destination approval, credential resolution, limits, usage accounting, and retry policy. Disable or bound library/executor/SDK retries so they cannot multiply gateway attempts. Bound the whole operation, not each request alone. Repairs share the same admitted call/token/time/budget limits. A lost response may still have cost money. Follow [uncertain-outcome recovery](../../inframeld-application-contracts/references/jobs-and-recovery.md#uncertain), not automatic replay.

Check cancellation during sampling, transforms, scenario construction, between cases, and before dispatch. Check the attempt fence, which identifies the worker still allowed to finish, before persistence. The Ragas executor's cancellation handle alone is too late for earlier model-capable preparation. Cancellation stops new work once observed. It cannot unsend a request. Keep completed results and account for late/uncertain charges without allowing an obsolete attempt to publish results.

Set **`RAGAS_DO_NOT_TRACK=true` before importing or using Ragas**. Its inspected [analytics implementation](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/_analytics.py) contains an opt-out-controlled network exporter. Disable external library callbacks/exporters and supply none of their credentials. Prompts, excerpts, answers, and secrets belong in protected evidence, not ordinary logs.

This disables library-owned export, not Inframeld's separately controlled operational/workload tracing. Project trace opt-out must not be bypassed by Ragas. Verify actual destinations with locked dependencies: flags and an in-process adapter are not a sandbox for arbitrary dependency code. Declare and prepare required tokenizer/assets explicitly. No hidden model downloads during a user's operation.

<a id="admit-and-bound-paid-work"></a>

<a id="cost"></a>

<a id="7-admit-and-bound-paid-work"></a>

## Admit and bound paid work

Generation review identifies sampled text/persona guidance and the selected generator. Evaluation review separately identifies pipeline calls and the judge receiving question, answer, and final context. Consenting to generation does not consent to a later evaluation charge.

Use gateway/LiteLLM prices when available for best-effort initial estimates, refine with actual inputs, and report gateway usage afterward. Do not assume one call per case: extraction, synthesis, claim extraction, support judgment, and repairs may be separate calls. Private-model prices may be unavailable. Local inference may have no external model API charge but still consumes resources.

The application-owned budget controls recorded in [Model spending controls](../../inframeld-application-contracts/references/spending-and-accounting.md#spending) apply at admission and dispatch. Preview estimates are not charge guarantees. Bound cases, input/output sizes, total calls/tokens, concurrency, elapsed time, and spending where prices permit it. An enabled monetary cap must not be weakened because prices are unknown. Apply the selected unknown-price admission policy and block when that policy requires it. Exhaustion stops new dispatch. Completed drafts/results remain available with incomplete counts. No hidden regeneration or retry outside accounting. Use existing job outcomes, not a new paused-job engine.

<a id="qualify-the-integration-and-judge"></a>

<a id="qualification"></a>

<a id="9-qualify-the-integration-and-judge"></a>

## Qualify the integration and judge

This documentation/source review installed no dependency, called no model, and ran no adapter/calibration tests. The following are future implementation obligations.

<a id="prove-routing-limits-and-failure-behavior"></a>

### Prove routing, limits, and failure behavior

Use recording gateway fakes and controlled integration tests for all preparation, extractors, synthesizers, claim extraction/judgment, repairs, optional embeddings, sync/async paths, and constructor defaults. Block and detect direct provider/telemetry calls, including when provider environment variables exist. Prove the starter preset makes no embedding calls and runs no default graph transforms.

Exercise actual structured schemas/context limits through supported providers and private gateways. Reject refusals, truncation, malformed structures, missing/duplicate verdicts, NaN, and incorrect types. Check intermediate claim counts and aggregation. Verify connection reuse needs no new credential and cannot change pipeline settings.

Test bounded retries/budgets, cancellation before executor creation and dispatch, stale-attempt persistence fences, restarts, and uncertain paid-call recovery. Exercise duplicate source text, changed chunking, truncated evidence, incompatible parser coordinates, revoked access, and source erasure. Repeat relevant checks after dependency changes.

Change a selected connection's access revision during generation, between comparison sides and after the last dispatched call but before finalization. Verify the operation preserves partial evidence, stops further sends and cannot claim a complete unchanged-environment comparison. Repeat with metadata-only rename and credential-only rotation to verify those changes do not themselves interrupt work. No test should make a historical access revision callable.

<a id="evaluation-setup-is-not-a-prerequisite-for-the-first-answer"></a>

### Evaluation setup is not a prerequisite for the first answer

[First-use setup](../../inframeld-architecture/references/first-use-and-private-defaults.md) needs working embeddings and generation. Alice needs neither a judge nor a benchmark of evaluation cases before asking her first question.

Optional starter generation and evaluation use embedded Ragas under [ADR-0051](../../../../docs/adr/ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md). Select generator and judge connections explicitly and independently of pipeline generation settings. Offer reuse of an existing authorized connection without another key. No provider or model is mandatory and no fallback is implicit. Generation needs no judge until the user explicitly requests evaluation.

[Evaluation's adapter contract](#gateway) covers structured-output conversion, every nested extraction/synthesis/judging/repair call, and optional future embeddings. Ragas receives no provider credentials or independent clients. ModelGateway keeps destination approval, authorization, credential resolution, limits, retry decisions, and usage accounting. Successful ordinary chat does not establish compatibility with the evaluation role's schemas or context limits. Source inspection supports this design. Runtime qualification remains required, without making optional preflight mandatory.

<a id="pending-decisions-for-dependent-implementation"></a>

## Decision references for dependent implementation

Apply the accepted entries below when their scope matches. Discuss only choices still explicitly marked pending:

- [PD-EVALUATION-03 (accepted): Qualify embedded Ragas without hidden calls or false confidence](decision-ragas-integration-and-calibration.md). Before implementing embedded generator/judge adapters or claiming supported model-quality/calibration results.
- [PD-ACCESS-02 (accepted): Keep durable work and credential lifetime explicit](../../inframeld-access-models/references/decision-admitted-work-authority.md). Before admitting, executing or resuming durable work that must interpret credential expiry, rotation, revocation or replacement.
