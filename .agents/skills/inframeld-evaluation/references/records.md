# Evaluation inputs, revisions and observations

<a id="evaluation-inputs-revisions-and-observations"></a>

Alice accepts a proposed question, then edits it. The edit creates a new unreviewed revision. An existing benchmark keeps its original revision, while each fresh run records exactly what executed and which metrics were available.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="evaluation"></a>

<a id="evaluation-frozen-inputs-and-recorded-observations"></a>

## Evaluation: frozen inputs and recorded observations

<a id="preserve-history-with-a-small-application-owned-model"></a>

### Preserve history with a small application-owned model

Alice generates starter questions, accepts one, and later edits its reference answer. The stable case ID connects its history. The edit creates a new unreviewed revision. A previously frozen benchmark still names the exact older revision. Evaluation owns these logical records. They are accepted design, not a statement that physical tables or APIs have been implemented.

| Concept | Minimum responsibility |
| --- | --- |
| **Generation provenance** | Pipeline/corpus snapshot, sampling policy/seed where applicable, requested count, selected source versions/artifacts/spans, preset/personas, Ragas version and prompts, generator connection ID/model settings, admitted and actual access-revision observations, actor/scope, durable job and unit outcomes, gateway calls/usage. Preserve scenario-to-source attribution, including partial generation and rejected candidates. |
| **Test case** | Stable pipeline-associated identity, active/removed state, current case revision, and generation provenance. Use it to browse history. It is not a separate generic dataset product. |
| **Case revision** | Immutable question, proposed reference answer, passage expectation, and bounded notes. Generated and edited content begins unreviewed. Editing never overwrites a revision already used in a benchmark. Manual blank-form authoring and automatic negative-case synthesis are deferred. |
| **Revision review** | Unreviewed, accepted, or rejected state for an exact revision, plus reviewer identity/kind, time, and bounded reason/history. Accepted is not automatically human-reviewed. Deferral preserves unreviewed state and review position. Content immutability does not mean the review decision cannot be recorded afterward. |
| **Passage expectation** | One source DocumentVersion, immutable parsed-artifact identity, typed source-coordinate spans, and protected excerpt or artifact reference sufficient to reconstruct it. The initial preset expects one complete passage. Generation-scoped chunk IDs, filenames, and text hashes alone are insufficient. |
| **Benchmark revision** | Immutable ordered case IDs and exact content revisions, review states at admission, and explicit regression/exploratory purpose. Default membership uses current accepted revisions of active cases only. Exploratory inclusion of unreviewed content must be explicit. Both comparison runs use the same snapshot. |
| **Evaluator revision** | Immutable library/version, prompt/rubric/schema identities, metric definitions and aggregation/failure rules, judge connection ID/model/settings. A run separately observes current access revisions and enforces their consistency. Generator provenance remains separate from judge configuration and pipeline generation settings. |
| **Evaluation run** | Exactly identified ready PipelineVersion or captured execution inputs, benchmark/evaluator revisions, initiating actor/effective scope, durable job status, timestamps, and complete counts. A comparison references two fresh runs and their paired metric coverage. Either side may use captured working settings. Neither a mutable working pointer nor an old score substitutes for fixed inputs and fresh execution. |
| **Per-case observation** | Run/case-revision identities. Execution outcome. Expected-passage coverage at retrieval, reranking/selection, and final context. Actual ordered evidence spans/chunks and cutoffs. Per-metric eligibility/status/reason/value/denominator. Bounded claim/verdict observations. Answer/citations/final-context artifacts. Observed model identities, gateway calls, duration and usage. Failed, cancelled, unscorable, and unattempted cases remain visible. |

A **rubric** defines scoring rules. A **schema** defines response structure. A **metric definition** names what is measured, its inputs, units, calculation, eligibility, and failure treatment. Ragas faithfulness is a claim fraction per case and a mean across successfully scored eligible cases, not the historical OpenEvals whole-answer boolean rate. Effective scope records the initiating actor's admitted access, not continuing permission to inspect content.

Start with stable case IDs and complete immutable snapshots. A revision can use a content hash as its identity, but the hash cannot replace protected content required for review. An evaluator revision can be saved configuration. These concepts need neither a table/aggregate per row in this list, a plugin registry, nor another execution engine. Accepted [PD-INDEXING-03](../../inframeld-indexing/references/decision-source-coordinates.md#approved-resolution) selects canonical conversion identity, coordinate units/ranges and logical segment mappings. Physical schema, indexes and concrete native/API representations remain delivery work within their owning boundaries.

Authorization uses six separately grantable actions on the exact owning Pipeline: `generate-evaluation-cases`, `view-evaluation-cases`, `edit-evaluation-cases`, `review-evaluation-cases`, `run-evaluation` and `inspect-evaluation-results`. Humans and applications may receive use. Applications cannot administer grants or audiences. Use the target-specific Pipeline grant model, without per-case grant rows or a generic Dataset/Experiment resource. Every protected read still checks current case audiences/sources. Review binds the exact revision and actual reviewer kind. Imported acceptance claims do not authorize acceptance. [Access](../../inframeld-access-models/references/actions-and-initial-grants.md#reviewed-capability-catalogue) owns eligibility. [Evaluation](generation-and-review.md#operation-authority) owns workflow checks. The [fixed creator assignments](../../inframeld-access-models/references/actions-and-initial-grants.md#initial-assignments) add all six actions and human-only `manage-evaluation-case-audiences`. [Evaluation](case-audiences.md#case-audiences) owns current group-management and audience revision checks.

The [fixed-input example](benchmarks-and-comparisons.md#input-reliability) connects these records. A run accepted with configuration 17, 12 exact document versions and 20 case revisions keeps those identities after later edits. The reference answer and expected passage belong to Evaluation. They are not forwarded into the Pipeline's query.

At a named measurement stage, 16 found cases, three not found and one unscorable case produce a passage score of 16/19. The run still contains its original 20 cases. Record why the missing mapping made that metric unscorable. Do not call it a retrieval miss or replace the benchmark with a smaller one. Other metrics have their own eligibility rules and denominators.

These fixed identities do not freeze permissions or shared connectivity and do not guarantee indefinite availability. A missing execution binding prevents execution against that input. A missing scoring mapping makes the affected metric unscorable. Neither permits substitution of a newer source/index. Protected projections may withhold identities and counts after revocation or erasure. Immutable membership is not a disclosure or content-retention bypass. These are constraints on the existing logical records, not new physical tables or wire fields.

<a id="do-not-replace-earlier-observations-with-later-results"></a>

### Do not replace earlier observations with later results

A later run must not overwrite earlier observations. Preserve attempt history when retrying under the job rules. A retry cannot quietly replace an unfavorable judgment with a better one.

Removed cases remain identifiable in authorized history until retention expires. Rejecting/removing content affects future selection, not old snapshots. Editing accepted content creates a new unreviewed revision and excludes it from new default benchmark assembly until accepted. Never silently select the older revision instead.

Current access and explicit source erasure apply to derived questions, references, excerpts, answers, and judgments too. Erasure can remove protected content sooner than normal retention. Mark it unavailable instead of promising reproducibility or preserving secrets through immutable snapshots. Evaluation records are separate from diagnostic traces. Neither store bypasses permission or retention policy.

Changing a question or expected meaning changes the benchmark input even if its stable case ID is unchanged. Compare both selected execution inputs against the same newly frozen benchmark, or select an unchanged subset and show how much it covers. Different case revisions are not the same regression test.

Each run keeps bounded final answers, final-context evidence or immutable artifacts from which it can be reconstructed, ordered source/chunk IDs, actual pipeline/model observations, call IDs, and usage. A hash alone cannot replace missing evidence bytes. Both comparison runs use the same frozen benchmark and evaluator revisions. Later edits do not relabel their history.

[Evaluation](generation-and-review.md) owns running, scoring, comparing, inspecting, and calibrating evaluations. Physical case-revision and comparison tables remain undecided. Do not create a table or repository merely because a concept has a name.

<a id="evaluation-application-boundaries"></a>

### Evaluation application boundaries

[ADR-0078](../../../../docs/adr/ADR-0078-separate-evaluation-case-work-run-coordination-and-scoring.md) separates case generation/review operations, run/comparison coordination and scoring adapters. Ordinary question execution stays with Pipelines, controlled progress with shared jobs and remote model calls with ModelGateway. Exact case/run, metric, progress and protected-result contracts remain to specify. The logical records do not imply a table or aggregate per concept.
