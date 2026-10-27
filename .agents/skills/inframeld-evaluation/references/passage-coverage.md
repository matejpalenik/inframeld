# Measure complete expected-passage coverage

Alice changes chunk boundaries between two configurations. A returned larger passage can still cover the expectation if verified source coordinates prove complete coverage. Missing mappings make the metric unscorable rather than a retrieval miss.

<a id="passage-identity-and-coverage"></a>

## Passage identity and coverage

Expected passages retain source version, parsed-artifact identity, source spans and reconstructible protected evidence, including generation-scenario attribution. Indexing supplies coordinates for the text actually returned, including any truncation.

Measure full union coverage at each named stage. Two chunks may together cover one expected passage even when boundaries changed. Chunk IDs, filenames and fuzzy resemblance do not prove equivalent passage identity.

Report missing mappings as unscorable counts separately alongside the scored denominator. For example, 16 covered cases among 19 mappable cases and one unscorable case are reported as 16/19 plus one unscorable, not 16/20. This is an illustrative calculation, not a measured result.

<a id="preserve-and-measure-passage-identity"></a>

<a id="passages"></a>

<a id="4-preserve-and-measure-passage-identity"></a>

## Preserve and measure passage identity

Suppose an expected passage occupies positions 100 through 180 in one parsed artifact. A returned chunk covering 80 through 200 satisfies it. Two adjacent chunks covering 100 through 140 and 140 through 180 also satisfy it. A chunk covering only 100 through 150 does not. These positions illustrate a common coordinate system, not a selected physical offset encoding. Indexing must define its units and interpretation.

Retain each expectation's DocumentVersion, immutable parsed-artifact identity, source spans, and protected excerpt or artifact reference sufficient to reconstruct it. Preserve the link from the sampled Inframeld passage to the Ragas scenario and returned case. Returned context text alone is not that link. Do not reconstruct identity by searching strings after generation: repeated sentences and parser changes make this ambiguous.

Chunks are generation-specific retrieval units, not stable expectations. Indexing owns their source mappings. Evaluation consumes those mappings and owns the metric.

<a id="measure-complete-coverage-at-a-named-stage"></a>

### Measure complete coverage at a named stage

For the initial single-passage preset, the passage is found only if the **union of permitted returned source spans completely covers the expectation** in the same proven coordinate system. Larger or adjacent chunks can satisfy it. Filenames, document IDs alone, chunk-ID equality, and fuzzy/semantic resemblance cannot substitute for coverage.

Validly mapped passages from other documents do not cover the expectation. When mappings are known and comparable, finding only those other passages is absent coverage (Not found), not an unsupported-mapping outcome.

Record three stages separately: initial retrieval, reranked or selected evidence, and the final context sent to generation. Include each stage's actual cutoff, passage count and reranking settings. If reranking is disabled, label the selection stage accordingly.

Context assembly keeps whole passages in ranked order. It stops at the first passage that will not fit, rather than truncating, summarizing or skipping it to fit later passages. Coordinate validation also applies to any supported transformed source representation. Never claim coverage for text that was not actually retained.

| Condition | Outcome |
| --- | --- |
| Comparable mappings and complete coverage | Found. |
| Comparable mappings but incomplete or absent coverage | Not found, an ordinary passage miss. |
| Expected source version/artifact unavailable, or parser output lacks verified coordinate mapping | Unscorable with a source/mapping reason, not a retrieval miss. |
| Access revoked or source erased | Protected content unavailable. Stop prohibited work and visibly exclude affected metrics without leaking excerpts in errors. |

For each stage, report found cases divided by successfully scored eligible cases, alongside admitted, eligible, failed, excluded, and unscorable counts. Zero denominator means no numeric score. A different valid passage may support a correct answer while the expected passage is absent. Coverage measures this expectation, not every valid answer. This application-owned deterministic calculation is not Ragas's LLM context-recall metric.

For example, at the **final-context stage**, 20 admitted cases can yield 16 found, three not found and one unscorable because its source mapping is unavailable. Report **16/19 scored cases**, plus the one unscorable case and its permitted reason. Do not report 16/20 as if the mapping problem were a retrieval miss, or silently present this as a complete 19-case benchmark. These counts assume the reader may inspect all 20 cases. If access has changed, protect the population as well as its details. This passage denominator does not determine the faithfulness or citation denominator.

## Follow one measurement

1. Resolve the expected passage in the frozen source version and its verified coordinates.
2. Identify the named stage, such as retrieval or final generation context. Use only that execution's actual passages.
3. Map returned passages to the same source and establish whether their union covers the whole expected span.
4. Record found, not found or unscorable with the reason. Missing mapping is not evidence of a miss.

This is accepted metric behavior. The canonical coordinate contract remains pending in [PD-INDEXING-03](../../inframeld-indexing/references/decision-source-coordinates.md). [Metrics and evidence](metrics-and-evidence.md) owns protected result populations and denominators. A teaching example does not establish a passage-coordinate schema.
