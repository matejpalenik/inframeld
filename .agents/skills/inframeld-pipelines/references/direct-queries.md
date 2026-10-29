# Try a question against captured working inputs

Alice tests a temporary override before Build. The direct query captures its effective settings and exact corpus, prepares what is needed and uses the ordinary answer path. It neither saves that override nor publishes traffic.

<a id="preview"></a>

<a id="direct-query"></a>

<a id="query-the-pipeline-directly"></a>

### Query the Pipeline directly

Suppose Pipeline `contracts` currently has revision 18. Alice runs `inframeld query --pipeline contracts` with retrieval top-k temporarily set to 12. Require Query on that Pipeline, then identify revision 18 and the effective override in the result. A Query grant on Deployment `contracts-production` is not sufficient. This request creates no Experiment, PipelineVersion or Deployment and cannot change production pointers, regardless of publication mode. Independently authorized live updates can still proceed.

1. Resolve the Pipeline and current working revision, apply only explicit permitted overrides, and resolve exact corpus revisions. Display the effective configuration, source scope, model destinations, required preparation, estimated cost and limits before admitting chargeable work. Model selections reference authorized connections, not arbitrary provider URLs or plaintext keys.
2. Save fixed effective settings and source/profile identities with an operation identity. Bind admission to the reviewed revisions. A changed configuration or corpus selection requires a fresh review, not a hidden substitution of latest values. Current permissions are checked, not frozen as an entitlement.
3. Ask Indexing to reuse compatible materializations or prepare missing ones through its ordinary jobs. Freeze the chosen complete prepared bindings before questions execute. An incomplete execution-input snapshot can record preparation progress, but cannot execute retrieval against unverified or mismatched indexes.
4. Execute through the same pipeline behavior used for live queries: gateway query embedding, permission-filtered retrieval, configured reranking, bounded context assembly and gateway generation. Preserve the [serving checks](answer-execution-and-receipts.md#serving) for current access, dependency health and temporary artifact pins without manufacturing a Deployment or PipelineVersion.
5. Return the answer with citations, usage and explicit direct-query attribution. Retain bounded execution provenance. Full diagnostic content is governed separately by tracing policy and inspection authority. [Evaluation](../../inframeld-evaluation/references/benchmarks-and-comparisons.md#comparison) owns explicitly requested benchmark results, not a hidden evaluation after every question.

Changing a prompt, generation model, reranker or retrieval limit usually reuses compatible existing indexes. Changing source selection, chunking or embedding meaning can require substantial preparation and paid calls. Show that work honestly. A direct query is not necessarily cheap, and local execution still consumes resources. A failed required shard, model or preparation step fails the query without switching models, searching an incompatible index or changing live traffic.

Each evaluation fixes its inputs for all cases. Revision 19 saved during a revision-18 evaluation affects only future operations. Comparisons may execute two execution-input snapshots, two ready versions, or one of each, freshly under Evaluation's frozen benchmark/evaluator rules. Historical scores are not fresh runs. Concurrent automatic source updates may still change Production independently. Direct querying does not pause those updates.

Query and trace inspection are independently scoped to the exact Pipeline or Deployment. A Pipeline Query grant permits its request and answer, not inspection of retained diagnostics. Pipeline trace inspection can include other callers' direct queries with current source access, but not production queries through that Pipeline's Deployments. [Access](../../inframeld-access-models/references/query-and-document-authorization.md#pipeline-query-authority) owns the accepted scopes and remaining machine mappings. Humans and applications may receive explicit grants. Direct Pipeline queries and evaluation do not enter production feedback counts.

Working configuration history, snapshots, evaluation evidence and diagnostic traces are different records, not unlimited archives. Active work receives bounded retention protection, not a permanent pin for every past query. Missing or erased dependencies produce explicit unavailability. A snapshot cannot recreate an opted-out trace or restore access to protected data.

The [trace lifecycle](query-tracing-and-privacy.md#trace-lifecycle) applies to direct Pipeline queries and live Deployment queries. If only diagnostic capture, storage or export fails, keep an otherwise successful query successful. Preserve confirmed permitted evidence and report partial or unknown diagnostics separately. Required authorization, budgets, receipts, audit and business persistence must still succeed.

Opting out stops further recording and queued diagnostic writes or delivery. It does not by itself cancel the query. Re-enabling tracing allows new eligible executions to record, but does not restart capture for this query. Explicitly deleting past traces is a separate operation: it blocks the affected reads before physical cleanup and does not change future recording.

None of these actions reruns a model, reconstructs a missing answer, expands receipt replay or grants trace inspection.

## Apply accepted PD-PIPELINES-01

Accepted [PD-PIPELINES-01](decision-execution-build-receipt-contracts.md#approved-resolution) selects this workflow's detailed contract. Alice starts a question using saved configuration 17. Bob saves configuration 18 while it runs. Separately, Production may serve a ready version using configuration 16. The application must keep each execution's chosen meaning and distinguish a ready build from permission to publish it. If an answer response is lost, a retry must not buy another answer. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.
