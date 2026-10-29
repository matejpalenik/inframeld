# Search only the permitted corpus

<a id="search-only-the-permitted-corpus"></a>

SupportBot may query Production but can read only SupportKnowledge. Retrieving globally and removing forbidden results afterward can miss the best permitted passages and expose protected populations. The search scope must be built from exact membership and current access first.

<a id="assemble-a-bounded-scope"></a>

## Assemble a bounded scope

1. Resolve the selected immutable corpus/materialization and its exact physical generations.
2. Intersect exact revision membership with current document access. PostgreSQL owns these facts. Caller-supplied group lists and mutable Chroma membership fields are not authority.
3. Build the supported server-generated filters and required shard set. An empty authorized scope performs no Chroma search. Invalid filters must never become unrestricted searches.
4. Query required shards with bounded fan-out. Merge only comparable candidates, using stable tie-breaking and the accepted scope limits.
5. Verify candidates and recheck current health/access at the documented boundaries before provider egress and disclosure.

Logical collections and physical shards are not one-to-one. A ready label alone cannot prove current health. Missing or failed required shards fail visibly instead of silently reducing the corpus, searching another engine or widening filters.

## Resolve and retain the exact binding

Accepted [PD-INDEXING-01](decision-capability-binding-contracts.md#approved-resolution) resolves a scoped IndexMaterialization and claims its operation pin atomically through the retention gate. Use its saved exact identities and current server-owned authorization to construct filters. The binding is not a permission certificate. Required missing or unusable dependencies fail visibly. Resolving an old binding cannot follow a mutable latest pointer, substitute a new generation or start hidden preparation. Recheck health/access at the accepted boundaries and release the pin only under the proven lifetime rules.

<a id="changed-state-and-failure-behavior"></a>

## Changed state and failure behavior

An admitted query protects exact artifacts with bounded pins, but pins do not freeze permission. Later revocation or erasure still applies. Global top-k followed only by permission checks is insufficient. Neither an oversized scope nor a failed backend filter justifies unbounded filter splitting or an alternate unfiltered query.

After successful Query authorization, no permitted documents means the ordinary no-evidence path without a vector search. A denied query or lost access to a protected result remains a denial. Access owns those distinct outcomes.

For R1={A1,B1} and R2={A1,B2}, each query searches only the generations corresponding to its captured revision and allowed documents. Keeping GB1 for old R1 does not make it eligible for R2. Shared storage does not merge logical membership.

<a id="retrieval"></a>

<a id="4-search-only-the-permitted-corpus"></a>

## Search only the permitted corpus

For each query, the application follows this sequence:

1. **Identify the caller and fixed execution inputs.** Authenticate the caller through the supported human or application path. Check project and operation-specific permissions. Live queries resolve a Deployment and exact PipelineVersion. Direct queries instead capture working settings under [Query on the exact Pipeline](../../inframeld-access-models/references/query-and-document-authorization.md#pipeline-query-authority). Evaluation uses its separately authorized admission and captured inputs. All identify exact verified bindings before search. Pipeline Query alone does not grant evaluation-history access.
2. **Keep the required data available.** In PostgreSQL, check that the profiles, layout, and materializations are healthy and ready. Register a time-limited operation pin, a record that prevents ordinary cleanup while this query uses them.
3. **Choose permitted generations.** Start with compatible generations from the fixed execution inputs' exact collection revisions. Keep only those allowed by current document groups and deletion state, then remove duplicates.
4. **Embed the question.** Request one query embedding for the selected profile through `ModelGateway`.
5. **Build the search filter.** The server includes `vectorization_generation_id: {"$in": [...]}` and the required immutable scope/profile restrictions.
6. **Search every required shard.** Limit simultaneous calls, use a shared deadline, and merge results using the same distance metric. Break ties by stable record ID and remove duplicates.
7. **Check before using the text.** Verify returned IDs and content references, current document permissions, and dependency health before sending text to a reranker, evaluator, model, or client. Check again before returning the result.

<a id="the-worked-examples-searchable-sets"></a>

### The worked example's searchable sets

“Eligible records” means records Chroma may consider. A nearest-neighbor query still returns only its bounded requested candidates, not every eligible record.

| Revision and current permissions | Generation filter | Eligible in S0 | Eligible in S1 |
| --- | --- | --- | --- |
| R1, A, B, C permitted | GA, GB1, GC | a1.1, b1.2, c1.1 | a1.2, b1.1, c1.2 |
| R2, A, B, C permitted | GA, GB2, GC | a1.1, b2.1, c1.1 | a1.2, b2.2, c1.2 |
| R2, B forbidden | GA, GC | a1.1, c1.1 | a1.2, c1.2 |
| R2, nothing permitted | Empty | No query | No query |

For the fully authorized R2 query, the adapter can construct this internal Chroma filter:

```json
{
  "$and": [
    { "organization_id": { "$eq": "O1" } },
    { "project_id": { "$eq": "P1" } },
    { "embedding_profile_id": { "$eq": "E1" } },
    { "processing_profile_id": { "$eq": "PP1" } },
    { "vectorization_generation_id": { "$in": ["GA", "GB2", "GC"] } }
  ]
}
```

**The caller does not submit this authoritative filter.** The server builds it from verified application state.

Send the same query embedding and permitted scope to **both S0 and S1** in LAYOUT1. One generation's chunks may occupy several shards. Naming a generation does not place all its records in one shard.

If B is forbidden, the server changes the `$in` list to GA, GC. No Chroma metadata write is needed. GB1 is excluded from R2 even for an authorized B reader because it is not part of R2's generation set.

<a id="merge-comparable-candidates-then-verify-them"></a>

### Merge comparable candidates, then verify them

Suppose the query needs two final candidates without reranking. Ask each shard for up to two candidates within the exact filter. Using the same cosine-distance metric, the illustrative results are:

| Shard | Candidates, smaller distance first |
| ----- | ---------------------------------- |
| S0    | b2.1: 0.08, a1.1: 0.15             |
| S1    | c1.2: 0.06, b2.2: 0.20             |

Merge, deduplicate record IDs, and use stable ID ordering for ties. The final two are **c1.2 and b2.1**. Verify their authoritative identities and current permissions before using the text.

The distances above are invented examples. Chroma's single-node HNSW index uses approximate nearest-neighbor search, which trades exhaustive comparison for faster retrieval. The filter defines exactly which records are allowed, but the search can still miss the closest ones. Tests must measure **recall**, how many of the exact nearest results it finds.

**If S1 fails, the query is unavailable.** Do not present S0's results as though the entire required corpus was searched.

<a id="empty-or-invalid-filters-must-never-become-unrestricted-searches"></a>

### Empty or invalid filters must never become unrestricted searches

An empty allowed set returns an authorized no-evidence outcome without querying Chroma.

This presumes the caller passed the query's project/action authorization. [Access distinguishes an empty evidence scope from denial](../../inframeld-access-models/references/query-and-document-authorization.md#empty-evidence-scope): a forbidden query or protected-content read still fails under its normal contract. Do not map every empty permitted set to an authorization error.

An empty or failed filter must never turn into an unrestricted search. Searching all records and discarding forbidden ones afterward is insufficient: forbidden or obsolete records may have crowded out the permitted candidates before they were returned.

Checking returned results provides another safeguard. It does not replace filtering the search itself.

<a id="permissions-remain-current"></a>

### Permissions remain current

Group membership and document allowlists stay in PostgreSQL. Fixed integration access uses the service principal's assigned groups. A supplied `userId` or canary affinity key cannot expand that authority. Authentication does not make Chroma metadata the permissions authority.

Unchanging manifests can be cached. A saved list of authorized generations can be reused only after checking that the relevant permission and group revisions are still current. Old collection revisions still use today's permissions. [Access](../../inframeld-access-models/references/authorization.md) owns these rules, so the vector adapter must not implement a second permission policy.

Check permissions again after any queue or budget wait, immediately before handing content to an external client or the code sending the response.

If revocation finishes before that check, block the send. If it finishes just after the check, the already-approved send may still happen and cannot be recalled. Later checks must stop further sends or results once they see the revocation. A database permission check and a network send cannot happen as one indivisible operation.

<a id="bound-the-combined-query-scope"></a>

### Bound the combined query scope

Limit the generation count, encoded filter size, number of conditions, shards searched, candidates returned, and total time. When a pipeline selects several collections, their combined scope must fit those limits.

If the scope is too large, return an explicit failure. Do not send a million IDs or keep splitting searches without a bound. A future design that splits filters would need to prove complete coverage, enough candidates from each part, and acceptable recall after merging. That work is deferred.

The MVP permits one processing profile and one embedding profile per pipeline. Combining scores from mixed profiles is deferred.

<a id="separate-historical-readiness-current-health-and-candidate-retries"></a>

### Separate historical readiness, current health, and candidate retries

A ready materialization passed its build checks. It can still become unavailable later, so queries must check current dependency health.

| Situation | Required behavior |
| --- | --- |
| **Backend outage, missing published records, or integrity conflict** | Make the affected dependencies unavailable. Historical readiness does not authorize serving from damaged or missing data. |
| **An unrelated candidate’s immutable insert has an uncertain outcome** | Keep healthy existing generations available. Do not mark the entire healthy index unavailable or force a Chroma restart. |
| **Safe candidate-write retry** | Retry the same frozen IDs and bytes within the configured budget. Current release A can continue while candidate B retries. |
| **Retry budget exhausted** | Fail B’s job visibly, retaining its identity and exhausted-budget reason. An explicit safe resume follows [Background jobs, retries, and competing changes](../../inframeld-application-contracts/references/jobs-and-recovery.md). |
| **Published numerical data is missing** | Use backup/restore or intervention. Do not silently reconstruct the index by calling the embedding model again. |

Use the [saved-write retry procedure](vector-writes-and-retries.md#retries) for unknown outcomes. Its job-ownership checks prevent an old attempt from publishing, but cannot cancel a request already sent to Chroma.

<a id="recheck-health-while-a-query-executes"></a>

### Recheck health while a query executes

Follow the [pin and health checks](retirement-and-erasure.md#retirement) before sending content or returning results. Earlier readiness cannot authorize use after a selected dependency fails.

Keep temporary saved batches for the required retry period, and keep unresolved-attempt evidence for cleanup. Neither makes a complete archive of published vectors. Product-level index reconstruction remains deferred.

Default onboarding uses this same build process. Creating default records does not make them ready. A real EmbeddingProfile still needs configured model settings. Changing publication mode may leave a ready build unpublished, which does not change Indexing's responsibility.

<a id="pending-decisions-for-dependent-implementation"></a>

## Accepted decision references for dependent implementation

Apply the accepted contract whose trigger matches. Qualification remains separate from policy approval:

- [PD-INDEXING-02 (accepted): Define what current index health can actually detect](decision-health-observation.md). Before implementing reconciliation, ongoing serving-health checks or claims about how quickly storage loss is detected.

<a id="status-and-sources"></a>

## Status and sources

The guide owns the accepted filter, recall, resource and failure qualification plans. No claim about a million-document workload, bounded latency or client interoperability follows from this explanation. Review current code and evidence before claiming those guarantees.

- [Indexing retrieval](profiles-and-preparation.md), [current Access](../../inframeld-access-models/references/authorization.md), [exact membership records](records.md#indexing) and [query execution](../../inframeld-pipelines/references/configuration-queries-and-builds.md).
- [Maintainer checks](profiles-and-preparation.md#maintainer-checks), [Knowledge corpus](../../inframeld-knowledge/references/collection-selection-and-batches.md#corpus) and [retention](../../inframeld-knowledge/references/deletion-and-retention.md).
