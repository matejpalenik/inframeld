# Generating, reviewing, and comparing pipeline tests

Alice has a working R.U.R. pipeline. She can finish setup now. Alternatively, she can ask Inframeld to propose 20 questions from her permitted documents, review their proposed answers and exact passages, and explicitly evaluate a ready version or her working configuration. Later, she can compare rerankers before building a release version, using the same saved questions.

This guide owns that behavior. **Evaluation** owns generation, review, benchmark snapshots, scoring, comparisons, and protected history. Knowledge owns source versions, Indexing owns processed text and source mappings, Pipelines owns execution, Access owns permissions, and ModelGateway owns model calls. Ragas is an embedded library, not another service or owner of application state.

> **Status:** [ADR-0051](../adr/ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md) accepts this design. Inspection of Ragas **v0.4.3** supports the adapter approach; no integration or calibration was executed. Runtime qualification below is still required. These workflows are not a claim that the backend or CLI implements them today.

[ADR-0052](../adr/ADR-0052-separate-experimental-execution-from-release-ready-pipeline-builds.md) additionally accepts evaluation of frozen working configurations before a release-ready build. It preserves the Ragas choice, scoring rules and fresh-comparison policy.

Direct execution means **Query on a Pipeline**. There is no separate Experiment resource. Evaluation saves the exact settings and corpus it will use. A fresh comparison may reuse those saved inputs, but must execute them again rather than reuse old scores.

Permission to query a Pipeline or inspect its traces does not grant unrestricted access to evaluation history. Evaluation evidence and query traces have separate access and retention rules.

## Contents

| Reader's question | Start here |
| --- | --- |
| Which permissions cover these operations? | [Six Pipeline-scoped actions](#operation-authority) |
| Where do cases come from? | [Generate starter cases](#generation) |
| What does acceptance mean? | [Review case revisions](#review) |
| What exactly executes? | [Freeze and execute](#comparison) |
| What if settings, cases or sources change? | [Fixed-input example](#input-reliability) |
| What counts as the right passage? | [Passage identity](#passages) |
| How are answers scored? | [Metrics](#metrics) |
| Which models and adapters are used? | [ModelGateway integration](#gateway) |
| What if a shared connection changes during a run? | [Connection consistency](#connection-consistency) |
| What work can charge? | [Cost and limits](#cost) |
| Can old results be inspected? | [Protected history](#history) |
| What remains unverified? | [Qualification](#qualification) |
| Can a score publish a version? | [Release authority](#release) |
| Which failures need a walkthrough? | [Maintainer checks](#maintainer-checks) |
| What is deferred? | [Decisions and scope](#decision-map) |

<a id="operation-authority"></a>

### Six separate permissions on the owning Pipeline

Alice may generate cases without being able to accept them, and SupportBot may run an evaluation without inspecting retained results. The [reviewed Access catalogue](access-control.md#reviewed-capability-catalogue) makes those independent grants on the exact Pipeline:

| Action | Evaluation behavior |
| --- | --- |
| `generate-evaluation-cases` | Separately admit generation/model work and save unreviewed candidate revisions. It does not run an evaluation. |
| `view-evaluation-cases` | Read protected cases/history and explicitly export permitted content. |
| `edit-evaluation-cases` | Edit/import, verify source linking and remove cases from future selection. Changed revisions are unreviewed. |
| `review-evaluation-cases` | Accept/reject an exact revision and record the actual reviewer identity/kind. Deferral does not accept it. |
| `run-evaluation` | Run with Pipeline Query plus current case, source, evaluator/model and budget checks. |
| `inspect-evaluation-results` | Read historical runs/comparisons under current audiences/sources, separately from diagnostic trace inspection. |

Humans and applications can receive use for each action; applications cannot grant permissions or administer audiences. Do not create a permission row per case or a generic Dataset/Experiment target. Case visibility still checks current audiences and sources on every read; neither a Pipeline grant nor an immutable benchmark bypasses that check.

Import requires editing authority and a reviewed protected destination audience, including for supported unresolved cases. Validate any supplied source links; unlinked content remains protected and cannot claim resolvable evidence. Imported acceptance claims never accept a revision. Export requires case-reading authority and current access to every exported item. Editing cannot widen an audience through its use grant. Human-only `manage-evaluation-case-audiences` on this Pipeline governs audience changes, with management of every old/new group. [Fixed creator assignments](access-contracts.md#initial-assignments) initialize all six operational actions and this separate administration action. The accepted action catalogue does not claim routes, tables or behavioral tests are implemented.

<a id="case-audiences"></a>

### Alice approves an audience and SupportBot imports cases

Alice has `manage-evaluation-case-audiences` on the HR Pipeline and manages HRPrivate. She saves HRPrivate as its nonempty, project-local future-import audience. SupportBot has `edit-evaluation-cases` on that Pipeline and imports questions/reference answers into this saved protection. The backend protects content immediately, including unresolved cases without linked sources. The import grant does not give the bot audience administration or document-reading access.

An application import must use the saved current human-approved audience; an explicit different audience is denied, not ignored or substituted. Review and capture the audience's identity/revision with the import. Recheck current binding, project/group state and required authority before saving; changed reviewed state conflicts rather than broadening disclosure. Human imports may explicitly review another protected destination audience only with the same Pipeline audience authority and group-management checks.

Changing the default from HRPrivate to SupportKnowledge requires the Pipeline action and management of every group in the authoritative old and proposed audiences, including removed, retained and added groups. Both audiences must remain nonempty and project-local. The default change affects future imports only. Existing cases retain their saved protection until a separately reviewed change identifies exact cases/revisions and old/new audiences. Save the protected change, expected-state checks and audit together using normal Access coordination. Do not infer management from edit/review grants or imported metadata.

Bob needs `view-evaluation-cases` on the Pipeline and access through the case's current audience to read it. Linking an HR-only source adds current source access: changing the case audience to SupportKnowledge cannot expose that source-backed case to a Support-only reader. Keep protection through edits/reimport and protect history, results and unresolved excerpts under the same current checks. Group deletion must not leave a live default or stored case protection dangling; relevant references must first be handled through their authorized lifecycle. Source erasure covers derived protected case content under the existing erasure rules.

New/changed content creates unreviewed revisions. Audience administration is not acceptance and never imports a foreign review as local authority. Exact content-review behavior beyond these invariants remains with the case contract; this audience decision does not invent a new review-reset rule. [ADR-0061](../adr/ADR-0061-control-evaluation-audiences-through-pipeline-authority.md) records the choice. [Logical records](data-model.md#evaluation) and [Access operation contracts](access-contracts.md#operation-contracts) distinguish accepted meaning from pending physical/wire schemas.

<a id="generation"></a>

## 1. Generate bounded starter cases

A **starter case** is a proposed question, reference answer, and expected source passage. A reference answer is a review aid, not a trusted answer key merely because a model wrote it. **Single-passage** means one passage should contain the evidence needed to answer; Ragas calls the corresponding synthesis strategy single-hop.

Generation is optional and separately admitted. Setup requires neither evaluation models nor tests. Its default completion action is **Finish**. Selecting generation does not start an evaluation or change the live pipeline.

1. Resolve the exact corpus from a selected ready pipeline version or a captured working-configuration selection. Check current document and model access. A release-ready version is not a prerequisite for starter generation, but its sampled text must already be processed and attributable. Any necessary source preparation is separately disclosed and admitted, not hidden inside synthesis.
2. Select a bounded sample from permitted, already processed text, distributed across documents and sections. Do not sample only the current retriever's successful results: that would omit retrieval failures from the proposed tests. Record the sampling policy, seed where applicable, selected spans, and unavailable or omitted sources.
3. Freeze source versions, parsed-artifact identities, passages, generator configuration, preset, and resource limits. Show scope and outgoing data before admission. This snapshot does not grant permanent permission to use its contents.
4. Run bounded keyphrase extraction and single-hop synthesis through the selected generator. Check cancellation and current access during preparation and before each model dispatch.
5. Validate candidate structure, size limits, and source attribution. Persist usable candidates as **unreviewed** with provenance. Report invalid candidates, shortfalls, and unit failures separately.

The default request is **20 cases**, not a guarantee of 20 valid or distinct cases. A small corpus may supply fewer suitable passages. Avoid exact duplicates within the batch; do not spend indefinitely regenerating to reach 20. Saved partial results remain reviewable.

### Use an explicit minimal preset

Configure `SingleHopSpecificQuerySynthesizer` with keyphrases as its selected property, explicit personas, and explicit gateway-backed model bindings. A **persona** describes the reader whose questions are being proposed. The preset supplies a general reader persona unless the user supplies bounded domain guidance; creating it must not invoke an undisclosed model.

Reuse Inframeld's processed text, not a second parser. This preset has **no additional generation-time embeddings and no relationship graph** linking passages. Ragas may hold passage nodes in memory; that does not introduce an application graph database or authorize its default graph-building transforms. Its default transform recipe does more work than this preset needs.

If a selected API requires an embedding object, bind a gateway adapter to the existing selected embedding connection rather than allowing a default client. The starter operation authorizes zero generation-time embedding calls: an unexpected call fails before dispatch, rather than spending outside the preset. Future embedding-assisted synthesis requires explicit model selection, disclosure, and budget.

The sample aims to cover several parts of the corpus; it is not statistically representative or certified ground truth. Automatic multi-hop and negative-case synthesis are deferred.

<a id="review"></a>

## 2. Review immutable case revisions

Alice sees a question about young Rossum, a proposed answer, and its actual excerpt with surrounding text. She need not type a passage from memory or select character offsets in the terminal.

A **TestCase** has a stable identity in one pipeline. Its immutable **case revision** contains the question, reference, and expectation. Review decisions apply to an exact revision and record reviewer and time. [Evaluation records](data-model.md#evaluation) defines these logical records, not mandatory separate database tables.

| Action | Result |
| --- | --- |
| **Accept** | Record an explicit authorized review decision for this exact revision. Interactive review displays the question, proposed answer, and resolvable exact passage first. Acceptance is not a model score or proof of correctness. |
| **Edit** | Create a new unreviewed content revision, even if the previous revision was accepted. Preserve old benchmark memberships. |
| **Reject** | Mark this revision rejected and exclude it from new benchmark admission; retain authorized history within retention. |
| **Later** | Leave the revision unreviewed and save review position. Do not accept or reject it. |
| **Remove** | Exclude the case from future benchmark selection without rewriting frozen snapshots. Removal is distinct from erasure. |
| **Finish review** | Save completed actions and return to the shell. Review can resume; evaluation does not start. |

Record who reviewed the revision and whether that reviewer was a human or an application. A script must specify the exact revision and the review action. A general spending-confirmation flag does not accept a case, and an automated decision must never be labelled human review.

An application may accept an exact case revision when it has explicit permission to do so. It still needs current access to the expected evidence, and that evidence must remain resolvable. These checks apply even without an interactive screen. The [reviewed Access catalogue](access-control.md#reviewed-capability-catalogue) supplies `review-evaluation-cases` on the exact Pipeline, with human/application use eligibility for acceptance and rejection. Separate human-only [case-audience administration](#case-audiences) and [fixed creator assignments](access-contracts.md#initial-assignments) are accepted; exact public/physical schemas remain delivery work. Application eligibility alone grants nothing.

Editing generated cases is in scope; manual authoring from a blank form is deferred. The initial expectation comes from generation. Any advanced evidence edit must select a resolvable source-backed passage through the application evidence contract, not substitute pasted text or a filename. It also creates an unreviewed revision. No terminal drag-selection interface is required for starter review.

The default regression benchmark selects the **current accepted revision of each active case**. After an accepted case is edited, that case is excluded from newly assembled default benchmarks until the new revision is accepted. Do not silently fall back to the old accepted revision. Existing frozen benchmarks remain unchanged and may be selected explicitly while their evidence remains available and permitted.

An explicit **exploratory** run may include unreviewed revisions. Label that fact and review states in admission, results, and exports. It does not promote their review state or constitute a reviewed regression benchmark. Rejected and removed cases are not silently restored.

<a id="dataset-portability"></a>

### Transfer datasets without transferring authority

Alice can explicitly export and import the test cases themselves, not just evaluator settings. The versioned Inframeld JSONL dataset contains the complete selected questions, reference answers, exact passage expectations, portable case/revision identities and their provenance. Evaluator settings remain in separate TOML files.

Dataset transfer excludes source documents, embeddings, runs, credentials and Deployment state. Ordinary configuration export contains no dataset content unless the user explicitly requests it.

Imported content is protected immediately by an explicitly reviewed destination group audience, including before sources are linked. Linking adds current source-access checks; it never removes the original imported protection. Retain protection through edits and reimport. Erasure and retention cover unresolved questions/references/excerpts too; exported external copies cannot be recalled.

Reuse unchanged previously imported revisions without duplication or resetting their review. New or deliberately adopted changed content creates unreviewed revisions. Local/incoming conflicts require a choice; old imports cannot silently roll back current content, and omission is not deletion. Imported selection is distinct from all locally stored cases and frozen benchmark membership. Provenance about source review never replaces explicit destination acceptance; eligible bulk acceptance identifies exact verified revisions.

Source linking proposes only verified permitted source-version/artifact/coordinate matches. Ambiguity requires a choice; missing or incompatible proof remains unresolved, not a fuzzy match or ordinary retrieval miss. Review mappings in groups but validate each expected passage. Never silently reduce a requested benchmark because some imported cases are unresolved. Document loading/preparation, linking, review and paid evaluation remain separate operations; Finish is the default after import.

See [configuration portability](configuration-portability.md) for packaging/orchestration and [the delivery plan](cli-delivery-plan.md) for specification gates covering exact JSONL identity, source proof, audience, action and recovery schemas. Evaluation owns these records and operations; the portability epic does not acquire a new domain.

<a id="comparison"></a>

## 3. Freeze inputs and execute explicitly

A **benchmark revision** fixes an ordered set of case revisions. An **evaluator revision** fixes metric definitions, prompts, library, judge, and settings. **Admission** means validating and saving the operation before a durable worker starts it.

1. Select a ready PipelineVersion or explicit direct Pipeline query execution of the working configuration, optionally with bounded temporary overrides. A retained execution-input snapshot may also supply exact comparison inputs while its dependencies remain available. Select accepted cases or an existing benchmark. With no eligible cases, explain why and create no paid run.
2. Select the judge explicitly, offering an existing connection. Show review coverage, configuration revision/overrides or version, corpus scope, required preparation, metrics, outgoing data, cost availability, and budget. Freeze effective execution inputs, benchmark/evaluator revisions and effective access conditions at admission. A later edit cannot change them.
3. For newly captured working-configuration inputs, resolve complete verified bindings through [ordinary direct-query preparation](pipelines-and-releases.md#preview). For a ready version or retained execution-input snapshot, verify its recorded bindings are still available; do not rebuild or replace missing historical bindings to make that input runnable. Then execute each question through the same pipeline behavior as live queries: query embedding, permission-filtered retrieval, configured reranking, final context assembly, and generation. **Do not send the reference answer or expected passage to the pipeline.** That would leak the answer into the system being tested. No question runs against incomplete or incompatible indexes.
4. Capture permitted evidence at each measured stage and the exact final context sent to generation. Calculate deterministic passage/citation signals, then judge eligible answers with Ragas faithfulness.
5. Save per-case outcomes and summaries including incomplete and failed cases. Generation, review, save, and build actions never silently start this run.

A run executes one exact version or execution-input snapshot for all its cases. A comparison executes **both baseline and candidate freshly** under identical frozen benchmark and evaluator revisions. Here candidate means the proposed comparison input, not necessarily a release candidate attached to a Deployment.

| Comparison inputs | Meaning |
| --- | --- |
| **Two execution-input snapshots** | Try two configurations, such as reranker A versus B, without creating a release-ready PipelineVersion. |
| **Ready version and execution-input snapshot** | Compare a fixed released/built baseline with the proposed working settings. Resolve a live baseline to its exact version before admission, not separately for each case. |
| **Two ready versions** | Preserve the existing post-build comparison workflow. |

For example, evaluation A captures working revision 17 with reranker A. Alice then saves revision 18 with reranker B. A continues using its original inputs. A new comparison may reference both snapshots but must execute both sides again; it does not subtract their old scores. Reuse compatible ready materializations, not historical answers or a newer corpus substituted behind a selected input. Revoked access or lost dependencies remain failures/unavailability, even for a retained snapshot.

Working-configuration evaluation records its effective overrides without saving them into the Pipeline. To ship the change, Alice explicitly saves the desired settings, then invokes Build on the Pipeline's current saved configuration. Build is not sourced from this run. Its review shows any mismatch in configuration, corpus or prepared inputs, including a sample evaluation versus full-corpus build. Matching input identity is not an automatic quality approval, and a mismatch does not create a compulsory judge call. [Pipelines](pipelines-and-releases.md#build) owns that boundary.

The existing [durable jobs](jobs-and-idempotency.md) own continuation, attempts, cancellation, and uncertainty. Closing a watcher does not repeat or cancel work. Reopening by operation/job ID finds saved progress. Checkpoint bounded preparation units and cases; do not keep a database transaction open during a model call.

<a id="input-reliability"></a>

### Keep the tested inputs fixed, not the caller's permissions

Alice starts a run on `contracts` with saved configuration 17, 12 exact document versions, 20 already accepted case revisions and her explicitly selected `quality-judge` connection. These are illustrative values, not defaults or a promise that generation yields 20 accepted cases. The admission review also discloses preparation, outgoing data, cost availability and budget. If reviewed inputs change before admission, report the conflict instead of silently accepting newer state.

After admission, a teammate saves configuration 18, uploads a newer contract and edits a case's reference answer. The admitted run still identifies configuration 17, its original corpus and the original case revision. An edit creates an unreviewed revision for future review. A newly assembled default benchmark excludes that case until its new revision is accepted; an existing frozen benchmark is not rewritten or silently replaced.

For the question "How long is the cancellation period?", the case may store the reference answer "30 days" and the expected cancellation clause in contract v3. The Pipeline receives the question through its normal execution contract, not either of those evaluation-only fields. Its retrieval must find evidence normally. Passage scoring consumes the expectation separately. Faithfulness uses the actual answer and only the final context sent to generation, never the reference answer or unused expected text as extra support.

| Change or missing input | Required behavior |
| --- | --- |
| Saved configuration, current case content or document latest-version pointer changes after admission | Keep the exact captured execution inputs and case revisions. Do not follow mutable pointers between cases. |
| A required historical execution binding or index is unavailable | Do not execute against incomplete dependencies, rebuild missing historical bindings or substitute a newer corpus. Report the blocked/failed work through existing run/job outcomes and preserve permitted saved results. Newly captured working inputs may still use their separately admitted ordinary preparation. |
| Execution dependencies are ready, but an expected passage lacks a verified source mapping | Mark the affected passage metric unscorable with its reason. This is not an ordinary retrieval miss or permission to declare other metrics successful. Each metric keeps its own eligibility checks. |
| Source access is revoked or evidence erased | Stop prohibited work and protect questions, references, answers, evidence, identifiers and aggregates. An old snapshot grants no continuing access. Do not reconstruct erased content. |
| A selected connection's access revision changes | Apply [connection consistency](#connection-consistency): stop further dispatch, retain actual observations and identify interrupted/changed-environment results. Do not use old connectivity or silently switch the remaining cases to new settings. Credential-only rotation and metadata-only rename retain their existing exceptions. |

Never silently remove a requested case because its evidence is unavailable. Preserve the admitted selection and unavailable outcomes under current access and retention, not an always-public count of that selection. A deliberate smaller selection is a new explicit admission, not a repair to the meaning of the old run. A fresh comparison executes both sides against the same frozen benchmark/evaluator and reports missing pairs rather than reusing earlier scores.

These rules use the existing execution framework. The [Evaluation contract](https://github.com/matejpalenik/inframeld/issues/140) still needs exact inputs, proof of source coordinates, failure representations and rules for which saved results a caller may see.

Implementation is divided into [execution](https://github.com/matejpalenik/inframeld/issues/143), [scoring](https://github.com/matejpalenik/inframeld/issues/69), [comparison](https://github.com/matejpalenik/inframeld/issues/68), [protected history](https://github.com/matejpalenik/inframeld/issues/70) and [CLI results](https://github.com/matejpalenik/inframeld/issues/180). [Evaluation qualification](https://github.com/matejpalenik/inframeld/issues/71) and the CLI qualification tickets must test the resulting behavior. This example defines no endpoint, permission identifier or physical table. [Evaluation records](data-model.md#evaluation) describes the logical relationships.

<a id="passages"></a>

## 4. Preserve and measure passage identity

Suppose an expected passage occupies positions 100 through 180 in one parsed artifact. A returned chunk covering 80 through 200 satisfies it. Two adjacent chunks covering 100 through 140 and 140 through 180 also satisfy it. A chunk covering only 100 through 150 does not. These positions illustrate a common coordinate system, not a selected physical offset encoding; Indexing must define its units and interpretation.

Retain each expectation's DocumentVersion, immutable parsed-artifact identity, source spans, and protected excerpt or artifact reference sufficient to reconstruct it. Preserve the link from the sampled Inframeld passage to the Ragas scenario and returned case. Returned context text alone is not that link. Do not reconstruct identity by searching strings after generation: repeated sentences and parser changes make this ambiguous.

Chunks are generation-specific retrieval units, not stable expectations. Indexing owns their source mappings; Evaluation consumes those mappings and owns the metric.

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
| Access revoked or source erased | Protected content unavailable; stop prohibited work and visibly exclude affected metrics without leaking excerpts in errors. |

For each stage, report found cases divided by successfully scored eligible cases, alongside admitted, eligible, failed, excluded, and unscorable counts. Zero denominator means no numeric score. A different valid passage may support a correct answer while the expected passage is absent. Coverage measures this expectation, not every valid answer. This application-owned deterministic calculation is not Ragas's LLM context-recall metric.

For example, at the **final-context stage**, 20 admitted cases can yield 16 found, three not found and one unscorable because its source mapping is unavailable. Report **16/19 scored cases**, plus the one unscorable case and its permitted reason. Do not report 16/20 as if the mapping problem were a retrieval miss, or silently present this as a complete 19-case benchmark. These counts assume the reader may inspect all 20 cases. If access has changed, protect the population as well as its details. This passage denominator does not determine the faithfulness or citation denominator.

<a id="metrics"></a>

## 5. Keep metrics separate

Ragas **Faithfulness** extracts factual claims from an answer, then judges whether the supplied context supports them:

```text
case faithfulness = supported claims / evaluated claims
run faithfulness = mean of successfully scored eligible case scores
```

Case scores of 3/4 and 1/1 produce a run mean of 0.875, not the pooled fraction 4/5. Keep claim denominators. The mean weights cases equally; it is not a boolean whole-answer pass rate or a confidence score.

Judge **only the final context actually sent to generation**, after reranking and whole-passage fitting. The question assists claim interpretation; unused documents and generated reference answers cannot supply additional support. Reference-answer correctness scoring is not selected for v1.

| Signal | Interpretation |
| --- | --- |
| **Passage coverage** | Stage-specific full expected-passage coverage as defined above. |
| **Faithfulness** | Per-case claim fraction and macro mean, with eligible, scored, failed, and unscorable counts. Support does not establish completeness, relevance, or truth outside the supplied source. |
| **Citation presence/validity** | Answered cases with at least one valid backend-derived citation divided by answered cases; count invalid citations separately. Identities must resolve to that execution's permitted evidence. Valid IDs do not prove claim support. |
| **Execution outcomes** | Answers, explicit abstentions, failures, cancellations, and unattempted cases across all admitted cases. Pipeline and judge failures remain distinct. |
| **Latency** | Query p50 (median) and p95 (95th percentile), with sample counts for completed answers/abstentions. Report failures/timeouts, judge time, and total time including queueing separately. Small samples do not establish production latency. |
| **Usage/cost** | Gateway calls, tokens, and observed/estimated charges, separated by pipeline execution, starter generation, and judging. Unknown values are not zero. |

There is no blended quality score. Show each denominator and exclusions. Completion says whether work finished, not that every metric was available or the pipeline passed.

<a id="result-presentation"></a>

### Make progress and results easy to inspect

For example, a 20-case run can finish with 18 answers, one explicit abstention and one failed query. If scoring failed for one of the 18 answers, faithfulness covers 17 answers, not 20. A result summary must identify that saved-but-unscored answer separately from the query that failed. "No answer returned" means an explicit pipeline abstention here, not a missing network response.

[CLI progress and result presentation](https://github.com/matejpalenik/inframeld/issues/175) presents those facts in ordinary language. Keep the admitted population, answering/scoring progress, per-case outcomes and saved results visible. In-progress counts name their denominator; "12 answered; 10 of those 12 scored" does not mean the other eight admitted questions have run. At completion or interruption, retain stage-specific passage coverage, faithfulness and its scored population, citation signals, failures/exclusions, latency sample counts and known/estimated/unavailable usage. The concise view may put additional stage, claim and pipeline-versus-judge details behind normal result inspection, but may not conceal missing observations or substitute a combined pass score.

Show a bounded list of cases needing attention, with stable case identity, permitted question text and a short reason such as "Answer saved; scoring failed", "Query failed" or "Not started". Make the full authorized list and individual saved answers/evidence available through ordinary paginated history inspection. Long questions can be shortened in the summary and read in full in the case view. Failed queries, abstentions, judge failures, canceled work, unscorable evidence and uncertain dispatch are different outcomes. Question text, identifiers and aggregate counts are protected too; never reveal an inaccessible population or reconstruct erased content for a friendly screen.

A budget stop with 17 fully completed cases and three not started retains the 17 results and names the remaining cases when permitted. If instead case 18 has an unknown paid-call outcome, identify that uncertainty and the two not-started cases; do not label all three safe to retry or suggest ordinary resume. Apply [job recovery](jobs-and-idempotency.md#progress-presentation) without repeating completed or uncertain model calls. Reading results never runs the pipeline or judge to fill missing data.

Reuse Evaluation's existing logical case/run observations and shared jobs. This is not a new data framework, generic work-item registry or status enum. #140 specifies the exact representation, #143 persists outcomes, #70 exposes protected reads and #180 displays them, with human/JSON parity qualified by #187. Contract and runtime qualification remain required.

| Situation | Required treatment |
| --- | --- |
| Explicit pipeline abstention | Faithfulness not applicable; retain outcome. |
| Answer with no usable final evidence | Unscorable, missing-evidence input failure; never 1.0. |
| No extracted claims, including a library NaN | Unscorable, no evaluable claims; neither 0.0 nor 1.0. |
| Complete valid judgments mark claims unsupported | A legitimate lower score, not an execution failure. |
| Refusal, malformed/truncated output, missing/duplicate claim judgments | Judge failure; never present a partial verdict list as complete. |
| Wrong types or non-finite/out-of-range score | Reject; no truthy-string conversion or silent clamping. |

Validate that each extracted claim has exactly one usable verdict under the pinned schema and that the score agrees with those counts. Save bounded claim text, verdicts, and explanations when produced. The inspected Ragas metric returns a score object, not a complete review record; the adapter must capture intermediate structured observations to enable inspection. Never fabricate missing explanations.

Answers and excerpts are untrusted input. Give the judge no tools, independent endpoints, or release authority. Structured output does not prevent prompt injection or prove that extraction found every claim. Calibration must test both extraction and support judgments.

<a id="gateway"></a>

## 6. Bind Ragas to ModelGateway

<a id="model-selection"></a>

### Select existing connections for separate roles

Starter generation and evaluation judging have separate explicitly selected bindings. Offer reuse of the pipeline's generation connection or another authorized saved connection without another key. Reuse is not implicit fallback. Generator and judge may share a connection; disclose that using the same model to generate and judge is not independent assessment.

These choices do not change pipeline generation, embedding, or reranking settings. No provider or model family is mandatory. Chat success does not prove support for the schemas, context size, and limits needed here. [Optional preflight](../adr/ADR-0050-make-model-preflight-optional-and-record-runtime-validation.md) stays optional; real work must still validate responses and report unsupported capabilities.

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

The service owns admission, authorization, snapshots, durable work, and results through application-owned protocols. Bootstrap constructs adapters. Domain/application contracts import no Ragas, LangChain, SDK, or vendor schema types. Adapters explicitly inherit their selected library interfaces; application protocol implementations also follow repository inheritance/override conventions.

| Adapter | Responsibilities |
| --- | --- |
| **Structured LLM** | Explicitly inherit `InstructorBaseRagasLLM`; implement `generate(prompt, response_model)` and asynchronous `agenerate(prompt, response_model)`. Convert library response models into application-owned gateway structured-output requests; validate responses and reconstruct the required library type. Set `is_async = True` on the asynchronous adapter because the inspected prompt path reads it. |
| **Embedding** | Explicitly inherit `BaseRagasEmbedding`; implement `embed_text` and asynchronous `aembed_text`, with bounded batches where required and the async capability signal used by consuming extractors. Route actual calls through an explicitly selected gateway binding. The starter preset authorizes none. |
| **Execution binding** | Fix selected connection IDs, model choices/settings, operation identity, deadline and budget. Observe current access revisions at admission and require them still current before each relevant dispatch; never select a historical access configuration. Gateway resolves the current authorized credential. Ragas receives neither the key nor its store. |
| **Boundary conversion** | Convert errors/results into named application outcomes. Keep vendor-specific types, schemas, and compatibility shims in infrastructure. |

Workers use asynchronous calls. Any exposed synchronous path must use the same gateway and must not block the event loop or create another provider client. Qualify the actual bridge against the gateway contract; do not assume a nested event loop is safe.

### Source-inspected compatibility, not a tested integration

Evidence below is from **v0.4.3**, inspected on 2026-09-29. Lock and test the whole dependency set. Rolling documentation may use different API shapes.

| Source | Integration consequence |
| --- | --- |
| [LLM interfaces](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/llms/base.py), [structured prompts](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/prompt/pydantic_prompt.py) | Modern typed generation supports a custom adapter path; prompt code also checks async capability. Method names alone are insufficient. |
| [Embedding interfaces](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/embeddings/base.py), [embedding extractor](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/testset/transforms/extractors/embeddings.py) | Modern and legacy APIs coexist. Verify the selected adapter against each consuming component. |
| [Metric base](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/collections/base.py), [Faithfulness](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/collections/faithfulness/metric.py) | The collection metric validates its LLM interface and uses it for extraction and support judgments. Capture intermediate results deliberately; handle missing claims/evidence explicitly. |
| [Generator](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/testset/synthesizers/generate.py), [single-hop strategy](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/testset/synthesizers/single_hop/specific.py), [sample construction](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/testset/synthesizers/single_hop/base.py) | Older annotations coexist with modern prompt support. Retain scenario/source identity outside returned text. The executor handle does not cover all earlier preparation. |
| [Synthesizer defaults](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/testset/synthesizers/base.py), [extractor defaults](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/testset/transforms/base.py), [default transforms](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/testset/transforms/default.py) | Defaults can construct provider clients or add embedding/graph work. A top-level custom LLM does not automatically bind every nested component. |

Explicitly bind every extractor, synthesizer, metric, prompt/repair path, and persona-generation path if later enabled. Give Ragas no provider credentials, independent provider/LiteLLM clients, or endpoints. Missing bindings must fail, not invoke default factories. No capability failure may silently select another model.

### Keep one security, retry, and telemetry boundary

<a id="connection-consistency"></a>

#### Observe shared connectivity without weakening frozen comparisons

Alice admits a comparison whose two sides use `company-gateway` access revision 7. A connection manager then activates revision 8. New work uses revision 8; the admitted comparison cannot keep calling revision 7 or silently finish the remaining cases under revision 8. Stop remaining model dispatches, preserve completed case outcomes with actual revision attribution and report an interrupted/incomplete comparison. Do not present its partial aggregate as a completed like-for-like improvement claim. To compare under revision 8, explicitly admit both sides freshly again, with normal cost review.

Capture the current access revision for every generator, pipeline and judge connection needed by the operation. Check it during preparation and before nested extraction, synthesis, judging and repair dispatches, including concurrent cases. Apply the same rule to reused historical snapshots and ready versions. Their definitions select connection identities and model settings, not old access revisions. An already-dispatched call may finish and incur cost; its result remains attributed to that revision, and uncertain outcomes cannot be automatically repeated.

At result finalization, check for relevant access changes since admission. If detected, retain the actually completed observations but label the run/comparison interrupted or changed-environment, not complete unchanged-environment evidence. The existing job outcomes apply: a known precondition failure is failed; an uncertain paid outcome needs recovery. A later update after a successfully finalized run does not rewrite its historical completion or scores, but future comparisons must disclose the changed environment. Credential-only rotation and metadata rename do not alone interrupt a run; record the credential revision actually used on each call.

This preserves frozen benchmark/evaluator and Pipeline inputs without granting historical connectivity. It also means Manual release mode freezes serving-version selection, not shared connection settings. [Model connections](model-connections.md#dispatch-freshness) owns dispatch and [ADR-0054](../adr/ADR-0054-use-shared-current-model-connections.md) owns the architectural change. No new configuration branch, job engine or Ragas client is introduced.

ModelGateway retains authorization, destination approval, credential resolution, limits, usage accounting, and retry policy. Disable or bound library/executor/SDK retries so they cannot multiply gateway attempts. Bound the whole operation, not each request alone. Repairs share the same admitted call/token/time/budget limits. A lost response may still have cost money; follow [uncertain-outcome recovery](jobs-and-idempotency.md#uncertain), not automatic replay.

Check cancellation during sampling, transforms, scenario construction, between cases, and before dispatch. Check the attempt fence, which identifies the worker still allowed to finish, before persistence. The Ragas executor's cancellation handle alone is too late for earlier model-capable preparation. Cancellation stops new work once observed; it cannot unsend a request. Keep completed results and account for late/uncertain charges without allowing an obsolete attempt to publish results.

Set **`RAGAS_DO_NOT_TRACK=true` before importing or using Ragas**. Its inspected [analytics implementation](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/_analytics.py) contains an opt-out-controlled network exporter. Disable external library callbacks/exporters and supply none of their credentials. Prompts, excerpts, answers, and secrets belong in protected evidence, not ordinary logs.

This disables library-owned export, not Inframeld's separately controlled operational/workload tracing. Project trace opt-out must not be bypassed by Ragas. Verify actual destinations with locked dependencies: flags and an in-process adapter are not a sandbox for arbitrary dependency code. Declare and prepare required tokenizer/assets explicitly; no hidden model downloads during a user's operation.

<a id="cost"></a>

## 7. Admit and bound paid work

Generation review identifies sampled text/persona guidance and the selected generator. Evaluation review separately identifies pipeline calls and the judge receiving question, answer, and final context. Consenting to generation does not consent to a later evaluation charge.

Use gateway/LiteLLM prices when available for best-effort initial estimates, refine with actual inputs, and report gateway usage afterward. Do not assume one call per case: extraction, synthesis, claim extraction, support judgment, and repairs may be separate calls. Private-model prices may be unavailable. Local inference may have no external model API charge but still consumes resources.

The application-owned budget controls recorded in [Model spending controls](model-connections.md#spending) apply at admission and dispatch. Preview estimates are not charge guarantees. Bound cases, input/output sizes, total calls/tokens, concurrency, elapsed time, and spending where prices permit it. An enabled monetary cap must not be weakened because prices are unknown; apply the selected unknown-price admission policy and block when that policy requires it. Exhaustion stops new dispatch; completed drafts/results remain available with incomplete counts. No hidden regeneration or retry outside accounting. Use existing job outcomes, not a new paused-job engine.

<a id="history"></a>

## 8. Protect history and compare fairly

Save generation provenance, review decisions, exact case revisions, benchmark/evaluator revisions, the selected PipelineVersion or execution-input snapshot and its corpus/bindings, effective access conditions, per-stage evidence, bounded answers, and per-case observations. Keep final context bytes or a reconstructible immutable protected artifact; a hash cannot replace missing evidence. Record gateway call IDs, admitted and actual connection access revisions, observed model identity where available, usage, and safe errors without credentials. These observations do not manufacture a live Deployment receipt or enter production feedback statistics.

**Current access governs every disclosure**, including generated questions/references derived from protected sources. Historic authorization is not a permission token. Recheck before sampling, model egress, and display/export. Revocation stops prohibited work and blocks protected results; preserve safe partial status. Access owns the [six accepted exact-Pipeline action identifiers](access-control.md#reviewed-capability-catalogue). [Audience administration](#case-audiences) and [fixed creator assignments](access-contracts.md#initial-assignments) are accepted. HTTP/physical schemas and endpoint mappings still need specification before implementation.

Source erasure and retention cover derived drafts, references, excerpts, answers, and judgments. Block access first, clean up resumably, and retain only permitted non-content markers showing unavailability. Immutability prevents silent edits, not authorized erasure. [Retention and deletion](retention-and-deletion.md) owns cleanup; evaluation retention periods are not implicitly the diagnostic trace default.

Evaluation records and diagnostic traces are **distinct stores**. Trace opt-out does not erase an explicitly requested benchmark/result, and evaluation persistence cannot justify a hidden trace stream. Disclose persistence at admission. Neither store bypasses access, retention, or erasure; local deletion cannot recall data already sent to providers.

### Compare compatible observations, showing missing pairs

Calculate paired changes only where both sides were successfully scored under compatible conditions. Show full admitted counts, each side's failures/exclusions, and paired count. Never claim improvement by discarding failed candidate cases.

| Comparison | Treatment |
| --- | --- |
| Same corpus, changed configuration | Same benchmark/evaluator and effective document scope; identify changed settings. |
| Changed chunking with preserved coordinates | Passage coverage remains comparable despite different chunk IDs. |
| Deliberate corpus/parser change | Label it; unavailable expected versions or unproved mappings are unscorable. Never retarget expectations silently. |
| Changed questions, metric definitions, or incompatible access | No like-for-like improvement claim; choose compatible inputs and rerun both sides. |
| Working-configuration sample compared with full-corpus behavior | Label the scope difference. Neither a successful sample nor matching model names validates an unevaluated full-corpus build. |
| Historical OpenEvals score | Retain its original evaluator identity. Never relabel boolean groundedness as Ragas faithfulness or calculate cross-definition improvement. |

Library, prompt/schema, model binding/settings, or metric changes produce a new evaluator revision. Both fresh runs use it. A matching remote alias does not prove unchanged provider behavior; record observed identity and disclose this limitation. Broad-access engineer results do not establish what a restricted bot will see.

<a id="qualification"></a>

## 9. Qualify the integration and judge

This documentation/source review installed no dependency, called no model, and ran no adapter/calibration tests. The following are future implementation obligations.

### Prove routing, limits, and failure behavior

Use recording gateway fakes and controlled integration tests for all preparation, extractors, synthesizers, claim extraction/judgment, repairs, optional embeddings, sync/async paths, and constructor defaults. Block and detect direct provider/telemetry calls, including when provider environment variables exist. Prove the starter preset makes no embedding calls and runs no default graph transforms.

Exercise actual structured schemas/context limits through supported providers and private gateways. Reject refusals, truncation, malformed structures, missing/duplicate verdicts, NaN, and incorrect types. Check intermediate claim counts and aggregation. Verify connection reuse needs no new credential and cannot change pipeline settings.

Test bounded retries/budgets, cancellation before executor creation and dispatch, stale-attempt persistence fences, restarts, and uncertain paid-call recovery. Exercise duplicate source text, changed chunking, truncated evidence, incompatible parser coordinates, revoked access, and source erasure. Repeat relevant checks after dependency changes.

Change a selected connection's access revision during generation, between comparison sides and after the last dispatched call but before finalization. Verify the operation preserves partial evidence, stops further sends and cannot claim a complete unchanged-environment comparison. Repeat with metadata-only rename and credential-only rotation to verify those changes do not themselves interrupt work. No test should make a historical access revision callable.

### Calibrate claim extraction and support judgments with humans

**Calibration** compares the selected judge with human-labelled evidence, not another model's opinion. Label factual claims and whether each is supported by the exact final context. Measure missed/altered claims separately from support-classification errors. Omitting an unsupported claim can inflate a score even when returned verdicts look valid.

Include supported and mixed-support answers, contradictions, numbers, negation, irrelevant-but-supported answers, abstentions, no-evidence/no-claim cases, long contexts, and prompt injection. Keep a held-out subset unused during tuning; record disputed labels and denominators. Numeric acceptance thresholds must be established and tested for this rubric; the old whole-answer agreement target does not transfer automatically.

Run five fixed borderline/adversarial examples three times each, keeping all results and reporting claim/score variation, failures, calls, cost, and latency. Never select favorable repeats. Temperature zero and deterministic arithmetic do not make a judge deterministic. Recalibrate after material library, prompt, model, language, or corpus changes. Changing judge after failure is an explicit choice, not automatic fallback.

<a id="release"></a>

## 10. Keep evidence separate from release authority

Evaluation is evidence, not permission to publish. Saving cases, completing a run, or receiving a webhook changes neither publication mode nor serving pointers.

In **Manual releases**, an authorized person/application explicitly requests release; readiness, expected deployment revision, permissions, and duplicate-request checks still apply. Record the evaluation reference and acknowledgment of missing or regressed evidence where required by the release workflow.

In **Automatic updates**, an authorized live-input source operation or explicit policy-controlled Build supplies authority independently of evaluation. Saving working configuration or completing direct-query preparation supplies none. A comparison neither pauses updates nor starts a hidden judge. Use Manual releases when the live version selection must remain fixed during review; this does not freeze shared connectivity. See [Pipelines and Releases](pipelines-and-releases.md#modes) and [connection consistency](#connection-consistency).

<a id="maintainer-checks"></a>

## 11. Maintainer checks

| Walkthrough | Expected outcome |
| --- | --- |
| Evaluate before any release-ready version exists | Capture captured working-configuration inputs, prepare verified dependencies and run explicitly without publication authority. |
| Edit working settings while evaluation runs | All cases keep the admitted effective configuration and corpus; subsequent edits affect later requests only. |
| Change selected shared access settings while evaluation runs | Stop further model dispatches; preserve partial results and actual revision attribution. A new explicit admission is required, with both comparison sides executed freshly. |
| Compare working settings with a live baseline | Resolve the baseline once, execute both sides freshly, and never follow changing live pointers per case. |
| Build after a temporary override or a sample test | Build uses saved settings and selected build corpus, discloses mismatches and does not claim the earlier run approved them. |
| Finish after setup | Pipeline remains usable; no generator, judge, tests, or evaluation charges required. |
| Reject every draft | No default benchmark can run; explain the absence of accepted cases. |
| Edit after benchmark freezing | New revision unreviewed; old snapshots unchanged, subject to erasure. |
| Change chunking | Complete mapped coverage can pass without equal chunk IDs. |
| Mapping unavailable | Unscorable, not ordinary retrieval miss. |
| Twenty cases produce 16 found, three misses and one unavailable mapping | At that named stage show 16/19 scored, the unscorable case and the original 20-case scope when permitted; do not shrink the benchmark or reuse that denominator for other metrics. |
| Historical execution binding disappears while a newer document/index exists | Report unavailability and preserve permitted partial results, without replacing or rebuilding the selected historical input. |
| Reference answer exists for a cancellation question | Execute only the question through ordinary Pipeline inputs; expected text cannot be injected into retrieval/generation or used as extra faithfulness support. |
| Revoke access during work/before history inspection | Stop prohibited sends and deny protected content, keeping safe partial status. |
| Erase a source | Derived protected test/evaluation content becomes unavailable under cleanup policy. |
| Unsupported selected model | Clear capability/output failure; no fallback. |
| Exhaust budget | No new paid dispatch; completed drafts/results and incomplete counts remain visible. |
| Cancel during keyphrase preparation | Cancellation applies there too, before a final executor handle exists. |
| Obtain 17 of 20 requested cases | Save 17 unreviewed drafts and report three missing/failed units; no unbounded regeneration. |
| Lose a provider response | Uncertain-outcome recovery, never silent replay of a potentially paid call. |
| Candidate judge fails once | Show failure and smaller paired coverage, not a false improvement. |
| Disable project tracing | No library export bypass; explicit evaluation records have their separately disclosed lifecycle. |

<a id="decision-map"></a>

## 12. Decisions and scope

[ADR-0051](../adr/ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md) replaces the historical [OpenEvals decision](../adr/ADR-0030-use-openevals-for-groundedness-evaluation.md). [ADR-0031](../adr/ADR-0031-compare-fresh-executions-against-frozen-benchmarks.md) still requires fresh comparisons; [ADR-0052](../adr/ADR-0052-separate-experimental-execution-from-release-ready-pipeline-builds.md) partially supersedes only its ready-version-only restriction. [CLI starter-evaluation journey](https://github.com/matejpalenik/inframeld/issues/179) illustrates starter evaluation and [CLI development loop](https://github.com/matejpalenik/inframeld/issues/172) the development loop; [the data model](data-model.md#evaluation) owns records.

Manual blank-form authoring, automatic multi-hop/negative synthesis, correctness/relevance judges, custom evaluator platforms, ensembles, optimizers, automatic remedies, and external Phoenix/LangSmith exporters remain deferred. These exclusions do not defer starter generation, review, or claim extraction. No hosted evaluation account, graph database, separate runner, or workflow engine is required.

Official background: [single-hop generation](https://docs.ragas.io/en/stable/howtos/applications/singlehop_testset_gen/), [prechunked input](https://docs.ragas.io/en/stable/howtos/customizations/testgenerator/prechunked_data/), [faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/), and [runtime configuration](https://docs.ragas.io/en/stable/howtos/customizations/run_config/). Use the pinned source evidence above when rolling examples have different API shapes.
