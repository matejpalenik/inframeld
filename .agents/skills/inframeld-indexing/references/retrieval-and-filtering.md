# Search only the permitted corpus

SupportBot may query Production but can read only SupportKnowledge. Retrieving globally and removing forbidden results afterward can miss the best permitted passages and expose protected populations. The search scope must be built from exact membership and current access first.

## Assemble a bounded scope

1. Resolve the selected immutable corpus/materialization and its exact physical generations.
2. Intersect exact revision membership with current document access. PostgreSQL owns these facts. Caller-supplied group lists and mutable Chroma membership fields are not authority.
3. Build the supported server-generated filters and required shard set. An empty authorized scope performs no Chroma search. Invalid filters must never become unrestricted searches.
4. Query required shards with bounded fan-out. Merge only comparable candidates, using stable tie-breaking and the accepted scope limits.
5. Verify candidates and recheck current health/access at the documented boundaries before provider egress and disclosure.

Logical collections and physical shards are not one-to-one. A ready label alone cannot prove current health. Missing or failed required shards fail visibly instead of silently reducing the corpus, searching another engine or widening filters.

## Changed state and failure behavior

An admitted query protects exact artifacts with bounded pins, but pins do not freeze permission. Later revocation or erasure still applies. Global top-k followed only by permission checks is insufficient. Neither an oversized scope nor a failed backend filter justifies unbounded filter splitting or an alternate unfiltered query.

After successful Query authorization, no permitted documents means the ordinary no-evidence path without a vector search. A denied query or lost access to a protected result remains a denial. Access owns those distinct outcomes.

For R1={A1,B1} and R2={A1,B2}, each query searches only the generations corresponding to its captured revision and allowed documents. Keeping GB1 for old R1 does not make it eligible for R2. Shared storage does not merge logical membership.

## Status and sources

The guide owns the accepted filter, recall, resource and failure qualification plans. No claim about a million-document workload, bounded latency or client interoperability follows from this explanation. Review current code and evidence before claiming those guarantees.

- [Indexing retrieval](../../../../docs/development/indexing.md), [current Access](../../../../docs/development/access-control.md), [exact membership records](../../../../docs/development/data-model.md#indexing) and [query execution](../../../../docs/development/pipelines-and-releases.md).
- [Maintainer checks](../../../../docs/development/indexing.md#maintainer-checks), [Knowledge corpus](../../../../docs/development/knowledge-lifecycle.md#corpus) and [retention](../../../../docs/development/retention-and-deletion.md).
