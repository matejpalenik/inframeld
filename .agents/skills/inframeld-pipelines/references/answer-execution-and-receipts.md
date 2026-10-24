# Execute an answer and preserve its attribution

SupportBot asks Production a question. The answer must use one selected version and only currently permitted evidence. If the response is lost, a retry must not silently buy another model answer or return protected stored text through an undeclared cache.

## Follow execution

1. Authenticate and authorize the exact query. Live serving selects one ready version and takes a bounded retention pin. A direct query uses captured working inputs with the same execution protections.
2. Retrieve exact captured-corpus evidence under current source access, verified filters and required-shard health. Required dependency failures remain visible.
3. Rerank and assemble the final generation context under the selected limits. Preserve the complete ranked prefix and whole-passage fitting contract. Record the actual text returned, including truncation/mapping consequences for Evaluation.
4. Set an explicit enforceable output allowance. Distinguish an unset temperature from an explicit value. A provider default is not zero. Unsupported settings fail instead of silently dropping parameters, shrinking output or issuing a continuation.
5. Dispatch embeddings and generation through ModelGateway with current approved access and credentials. Recheck current authority and dependency health before egress and protected disclosure.
6. Record the actual selected version and every final source, including uncited evidence, before releasing the response under the receipt contract.

Mid-query Pipeline edits or releases do not reroute the captured operation.

Relevant shared connection-access changes stop further dispatch. Already sent calls retain actual attribution. Failed required shards, credentials or reranking cannot authorize an alternate provider or unfiltered fallback.

## Receipts and uncertainty

An AnswerReceipt records limited live-answer attribution, not a full-answer archive.

Default-route retries locate the original logical-route operation before resolving a newly bound target. Otherwise an alias change could start another paid query.

After current authentication and authorization, completed lost-answer replay returns the documented receipt-only outcome. It does not regenerate the answer. Query provenance, Evaluation evidence and policy-controlled diagnostics have different access and retention rules. Neither snapshot IDs nor receipts bypass them.

A lost provider response does not prove no work or charge occurred. A SQL lease cannot cancel remote work. Keep uncertain paid dispatch distinct from cancellation, a lost CLI connection and an ordinary completed result. Do not choose another provider as recovery.

## Validation evidence

Separate synthetic model preflight is optional. Complete configuration and genuinely verified materializations can reach first publication while generation remains untested. Real calls retain mandatory security, spending and response checks.

Only successful actual role/model/configuration and connection/credential revisions gain validation evidence. Historical success is not release authority or current provider health.

Credential rotation makes old evidence inapplicable without requiring a fresh synthetic call. Missing required credentials or invalid embeddings still fail. A stale or absent validation marker alone does not block otherwise valid use.

## Status and sources

These are accepted execution and replay contracts. Inspect implementation before claiming exact HTTP shapes, latency or interoperability. Native OpenAPI and owning guides supply the actual delivered contract.

- [Answer flow](../../../../docs/development/pipelines-and-releases.md), [generation context](../../../../docs/development/pipelines-and-releases.md#generation-context-contract), [generation parameters](../../../../docs/development/pipelines-and-releases.md#generation-parameters) and [receipt records](../../../../docs/development/data-model.md#pipelines).
- [Jobs and answer recovery](../../../../docs/development/jobs-and-idempotency.md), [gateway dispatch](../../../../docs/development/model-connections.md#dispatch-freshness), [model roles](../../../../docs/development/model-connections.md#roles), [validation evidence](../../../../docs/development/data-model.md#model-validation-evidence) and [ADR-0050](../../../../docs/adr/ADR-0050-make-model-preflight-optional-and-record-runtime-validation.md).
