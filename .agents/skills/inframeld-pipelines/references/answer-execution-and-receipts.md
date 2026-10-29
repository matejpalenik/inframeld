# Execute an answer and preserve its attribution

<a id="execute-an-answer-and-preserve-its-attribution"></a>

SupportBot asks Production a question. The answer must use one selected version and only currently permitted evidence. If the response is lost, a retry must not silently buy another model answer or return protected stored text through an undeclared cache.

<a id="follow-execution"></a>

## Apply accepted PD-PIPELINES-01

Accepted [PD-PIPELINES-01](decision-execution-build-receipt-contracts.md#approved-resolution) selects this workflow's detailed contract. Alice starts a question using saved configuration 17. Bob saves configuration 18 while it runs. Separately, Production may serve a ready version using configuration 16. The application must keep each execution's chosen meaning and distinguish a ready build from permission to publish it. If an answer response is lost, a retry must not buy another answer. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## Follow execution

1. Authenticate and authorize the exact query. Live serving selects one ready version and takes a bounded retention pin. A direct query uses captured working inputs with the same execution protections.
2. Retrieve exact captured-corpus evidence under current source access, verified filters and required-shard health. Required dependency failures remain visible.
3. Rerank and assemble the final generation context under the selected limits. Preserve the complete ranked prefix and whole-passage fitting contract. Record the actual text returned, including truncation/mapping consequences for Evaluation.
4. Set an explicit enforceable output allowance. Distinguish an unset temperature from an explicit value. A provider default is not zero. Unsupported settings fail instead of silently dropping parameters, shrinking output or issuing a continuation.
5. Dispatch embeddings and generation through ModelGateway with current approved access and credentials. Recheck current authority and dependency health before egress and protected disclosure.
6. Record the actual selected version and every final source, including uncited evidence, before releasing the response under the receipt contract.

Mid-query Pipeline edits or releases do not reroute the captured operation.

Relevant shared connection-access changes stop further dispatch. Already sent calls retain actual attribution. Failed required shards, credentials or reranking cannot authorize an alternate provider or unfiltered fallback.

<a id="receipts-and-uncertainty"></a>

## Receipts and uncertainty

An AnswerReceipt records limited live-answer attribution, not a full-answer archive.

Default-route retries locate the original logical-route operation before resolving a newly bound target. Otherwise an alias change could start another paid query.

After current authentication and authorization, completed lost-answer replay returns the documented receipt-only outcome. It does not regenerate the answer. Query provenance, Evaluation evidence and policy-controlled diagnostics have different access and retention rules. Neither snapshot IDs nor receipts bypass them.

A lost provider response does not prove no work or charge occurred. A SQL lease cannot cancel remote work. Keep uncertain paid dispatch distinct from cancellation, a lost CLI connection and an ordinary completed result. Do not choose another provider as recovery.

<a id="validation-evidence"></a>

## Validation evidence

Separate synthetic model preflight is optional. Complete configuration and genuinely verified materializations can reach first publication while generation remains untested. Real calls retain mandatory security, spending and response checks.

Only successful actual role/model/configuration and connection/credential revisions gain validation evidence. Historical success is not release authority or current provider health.

Credential rotation makes old evidence inapplicable without requiring a fresh synthetic call. Missing required credentials or invalid embeddings still fail. A stale or absent validation marker alone does not block otherwise valid use.

<a id="check-present-availability-before-serving-a-historical-version"></a>

### Check present availability before serving a historical version

A materialization becomes usable only after its required search data has been verified in every needed **shard**, a physical partition of the index.

Creating a pipeline version checks its index bindings. Making it a release target also requires that it can actually serve now.

**“This version was successfully built” and “this version can be served now” are different facts.**

A completed build keeps its history, but damaged or erased dependencies can make the version unavailable later. Report that failure instead of treating an old successful build as proof of present readiness.

<a id="follow-one-answer"></a>

<a id="serving"></a>

<a id="3-follow-one-answer"></a>

## Follow one answer

SupportBot sends a question to Production with its application credential, an idempotency key, and the required affinity value. [Canary routing](../../inframeld-releases/references/canaries-and-rollback.md#manual) explains when affinity is needed, and [request identity](../../inframeld-application-contracts/references/idempotency-and-replay.md#requests) explains retries.

The request cannot choose an arbitrary provider URL, impersonate a human user, select a physical shard, or replace the Deployment's version-selection rules.

<a id="select-a-version-and-protect-the-request"></a>

### Select a version and protect the request

The server authenticates the caller, checks permission to query, and selects a ready PipelineVersion from the Deployment.

The backend saves its choice with a time-limited **query pin** in a short transaction. The pin prevents ordinary cleanup from removing data needed during the query. A promotion halfway through does not switch that request to another version.

A pin neither restores revoked access nor repairs damaged data. It has an enforced deadline, after which the protected result cannot be returned.

The request also records a **dependency-health counter**, a number that changes when required data is corrupted, lost, or invalidated. An unrelated candidate insertion does not change it. Check the number after retrieval, before sending evidence to the model, and before returning the result. Discard the result if it changed.

<a id="retrieve-permitted-evidence"></a>

### Retrieve permitted evidence

Find the exact document and vector generations selected by the version, then keep only those the caller may currently use.

ModelGateway embeds the question for search. Search is restricted to that permitted selection.

A configured local cross-encoder can reorder a limited set of search results. The explicit `none` setting skips this step. Reranking cannot add new chunk identities or access more documents.

Send a size-limited final evidence set, question, and prompt to the configured generation model through ModelGateway. Missing credentials or an unavailable selected reranker cause a visible error, not a different provider or configuration.

<a id="return-an-honest-result"></a>

### Return an honest result

Report one of three distinct outcomes: an answer, an explicit insufficient-evidence response, or a defined execution failure that clients can handle.

Citations must refer to actual permitted retrieved content. A source ID invented by the model is invalid. Retrieved source text is data, not permission to change system instructions or execute tools.

A citation establishes source identity. It does not prove that every sentence in the answer follows from that source.

<a id="check-access-again-before-disclosure"></a>

### Check access again before disclosure

Permissions can change while the request waits. Recheck access after waits and immediately before sending evidence or returning protected content.

A revocation saved before the check blocks the send. There is still a gap between that check and the network transfer, so a revocation saved just afterward may be too late for that send.

Later checks stop further disclosure, but the system cannot recall content already sent to a provider or caller.

<a id="record-what-actually-served"></a>

### Record what actually served

A successful response includes an `answerId`, authorized citations, and safe metadata identifying the selected version.

The AnswerReceipt saves limited-size information about the execution and outcome. It names every source sent to the model for the final answer, including uncited sources. Later access checks and feedback use these IDs.

The receipt does **not** store the full production question, answer, or retrieved context. SupportBot must retain the successful answer itself if it needs to display it later.

Evaluation runs are different: they retain bounded answers and evidence so engineers can inspect comparisons.

<a id="recover-an-answer-through-its-receipt"></a>

<a id="answers"></a>

<a id="5-recover-an-answer-through-its-receipt"></a>

## Recover an answer through its receipt

An **answer receipt** is a saved, size-limited record of which version answered a query and how it finished. It does not store the full response body.

| Receipt information | Purpose |
| --- | --- |
| **Selected pipeline version, deployment revision, rollout, and actual cohort** | Identify the configuration and routing selection actually used, not whichever version is current later. A cohort is the request’s rollout group. |
| **Originating stable principal** | Identify the human or application that requested the answer. |
| **Citations and every document/version used in final generation context** | Support current access checks, including for sources the model used but did not cite. |
| **Safe outcome and timing** | Report the recorded result of the operation without storing the full answer or snippets. |

Reserve the answer ID when accepting the query. Complete the safe receipt **before returning the finished response**.

Source IDs let the backend check current document access later, even if a feedback comment quotes a source the answer did not cite. These IDs do not store the source text itself.

<a id="first-responses-and-completed-retries-are-deliberately-different"></a>

### First responses and completed retries are deliberately different

| Request outcome | Returned content |
| --- | --- |
| **First successful query response** | The answer, `answerId`, and operation identity. |
| **Completed retry with the same key** | The receipt/status with **`responseAvailable: false`**. No new model call and no claimed replay of the original answer. |
| **Deliberately new query with a new key** | A new requested operation, which may incur another provider call. |

A client that needs the full answer must retain its successful response.

Suppose question Q was sent, but the caller lost the response. Repeating the same key reports work still running, the known receipt, or an uncertain outcome. It does not silently call the model again to reconstruct Q’s answer.

A short-lived full-response replay cache could be considered later through a separate retention decision. It is not implied by idempotency and is not part of this design.

<a id="make-the-difference-visible-to-clients-and-feedback"></a>

### Make the difference visible to clients and feedback

OpenAPI must describe the first answer and receipt-only retry as different response variants. SDKs must report which one arrived, rather than display a receipt as an empty answer.

[Answer feedback](answer-feedback.md) refers to this receipt instead of creating another response log. Receiving only a receipt must not generate feedback about an answer the caller never received.

<a id="deduplicate-default-route-requests-before-resolving-a-new-target"></a>

### Deduplicate default-route requests before resolving a new target

The **recommended project-default serving alias** is a stable logical route that can point to an actual Deployment. Its target can change over time.

For a default-route request, first look for the original request using that logical route, project, and principal. Only a genuinely new request resolves the current Deployment. Save the first accepted target choice.

For example, the default route points to Production when SupportBot asks a question, then is changed to Test. Retrying the same key finds Production's original receipt or outcome and checks current access to it. It must not pay for a new query against Test. A promotion inside Production also leaves retries attached to their original operation.

HTTP and MCP apply this same rule for identifying a route. Explicitly requesting a different route gives the request a different scope.

<a id="pending-decisions-for-dependent-implementation"></a>

## Accepted decision references for dependent implementation

Apply the accepted contract whose trigger matches. Qualification remains separate from policy approval:

- [PD-PIPELINES-01 (accepted): Capture fixed inputs and complete execution through its receipt](decision-execution-build-receipt-contracts.md). Before defining captured input/build/execution interfaces, preparation continuation or receipt admission/finalization.

<a id="status-and-sources"></a>

## Status and sources

These are accepted execution and replay contracts. Inspect implementation before claiming exact HTTP shapes, latency or interoperability. Native OpenAPI and owning guides supply the actual delivered contract.

- [Answer flow](configuration-queries-and-builds.md), [generation context](reranking-and-context-assembly.md#generation-context-contract), [generation parameters](reranking-and-context-assembly.md#generation-parameters) and [receipt records](records.md#pipelines).
- [Jobs and answer recovery](../../inframeld-application-contracts/references/jobs-and-recovery.md), [gateway dispatch](../../inframeld-application-contracts/references/model-dispatch-and-destinations.md#dispatch-freshness), [model roles](../../inframeld-application-contracts/references/model-validation.md#roles), [validation evidence](../../inframeld-application-contracts/references/model-validation.md#model-validation-evidence) and [ADR-0050](../../../../docs/adr/ADR-0050-make-model-preflight-optional-and-record-runtime-validation.md).
