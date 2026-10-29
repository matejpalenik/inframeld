# Generate starter cases and review exact revisions

<a id="generate-starter-cases-and-review-exact-revisions"></a>

Alice has working Support knowledge but no useful regression tests. Generation proposes questions, references and expected passages. Alice reviews them before they become the default benchmark population. Generating a plausible question is not evidence that the Pipeline answers it correctly.

<a id="follow-bounded-generation"></a>

## Apply accepted PD-EVALUATION-01

Accepted [PD-EVALUATION-01](decision-case-review-contracts.md#approved-resolution) selects this workflow's detailed contract. Generating a question, editing it and approving it are different actions. Approval should apply only to what someone actually reviewed. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## Follow bounded generation

1. Freeze a permitted corpus sample across documents and sections. Sampling only successful retrieval hits would hide passages retrieval already misses.
2. Reuse processed text with explicit personas, keyphrases and single-hop synthesis. The starter request is 20 single-passage cases. It adds no generation-time embeddings, reparsing or relationship graph.
3. Route extraction, synthesis, judging and repairs through ModelGateway using explicit generator/judge bindings. Reusing an authorized saved connection needs no second key and does not change Pipeline generation settings.
4. Save proposed immutable revisions as unreviewed. Preserve expected source-version/artifact spans and generation scenario attribution.
5. Show shortfalls and partial failures. Do not regenerate without bounds until the requested count is reached or start evaluation implicitly.

Generated questions and reference answers can reveal their sources. They inherit source protection and erasure obligations. Generation is optional after setup. Finish remains the default completion action, and the first useful pipeline requires neither generation nor a judge.

<a id="review-changes-meaningfully"></a>

## Review changes meaningfully

Accept, edit, reject, defer and remove have distinct meanings in the owning contract. Acceptance binds an exact revision. Editing creates a new unreviewed revision.

Previously frozen benchmarks retain their original revisions, subject to erasure. Default regression membership uses currently accepted revisions. Exploratory inclusion of unreviewed cases is explicit and labelled.

Manual blank-form authoring remains deferred. Generation, review and evaluation are separate application operations shared by the CLI and future Studio. Neither reviewing cases nor a favorable comparison saves Pipeline settings or starts publication.

<a id="operation-authority"></a>

<a id="six-separate-permissions-on-the-owning-pipeline"></a>

### Six separate permissions on the owning Pipeline

Alice may generate cases without being able to accept them, and SupportBot may run an evaluation without inspecting retained results. The [reviewed Access catalogue](../../inframeld-access-models/references/actions-and-initial-grants.md#reviewed-capability-catalogue) makes those independent grants on the exact Pipeline:

| Action | Evaluation behavior |
| --- | --- |
| `generate-evaluation-cases` | Separately admit generation/model work and save unreviewed candidate revisions. It does not run an evaluation. |
| `view-evaluation-cases` | Read protected cases/history and explicitly export permitted content. |
| `edit-evaluation-cases` | Edit/import, verify source linking and remove cases from future selection. Changed revisions are unreviewed. |
| `review-evaluation-cases` | Accept/reject an exact revision and record the actual reviewer identity/kind. Deferral does not accept it. |
| `run-evaluation` | Run with Pipeline Query plus current case, source, evaluator/model and budget checks. |
| `inspect-evaluation-results` | Read historical runs/comparisons under current audiences/sources, separately from diagnostic trace inspection. |

Humans and applications can receive use for each action. Applications cannot grant permissions or administer audiences. Do not create a permission row per case or a generic Dataset/Experiment target. Case visibility still checks current audiences and sources on every read. Neither a Pipeline grant nor an immutable benchmark bypasses that check.

Import requires editing authority and a reviewed protected destination audience, including for supported unresolved cases. Validate any supplied source links. Unlinked content remains protected and cannot claim resolvable evidence. Imported acceptance claims never accept a revision. Export requires case-reading authority and current access to every exported item. Editing cannot widen an audience through its use grant. Human-only `manage-evaluation-case-audiences` on this Pipeline governs audience changes, with management of every old/new group. [Fixed creator assignments](../../inframeld-access-models/references/actions-and-initial-grants.md#initial-assignments) initialize all six operational actions and this separate administration action. The accepted action catalogue does not claim routes, tables or behavioral tests are implemented.

<a id="generate-bounded-starter-cases"></a>

<a id="generation"></a>

<a id="1-generate-bounded-starter-cases"></a>

## Generate bounded starter cases

A **starter case** is a proposed question, reference answer, and expected source passage. A reference answer is a review aid, not a trusted answer key merely because a model wrote it. **Single-passage** means one passage should contain the evidence needed to answer. Ragas calls the corresponding synthesis strategy single-hop.

Generation is optional and separately admitted. Setup requires neither evaluation models nor tests. Its default completion action is **Finish**. Selecting generation does not start an evaluation or change the live pipeline.

1. Resolve the exact corpus from a selected ready pipeline version or a captured working-configuration selection. Check current document and model access. A release-ready version is not a prerequisite for starter generation, but its sampled text must already be processed and attributable. Any necessary source preparation is separately disclosed and admitted, not hidden inside synthesis.
2. Select a bounded sample from permitted, already processed text, distributed across documents and sections. Do not sample only the current retriever's successful results: that would omit retrieval failures from the proposed tests. Record the sampling policy, seed where applicable, selected spans, and unavailable or omitted sources.
3. Freeze source versions, parsed-artifact identities, passages, generator configuration, preset, and resource limits. Show scope and outgoing data before admission. This snapshot does not grant permanent permission to use its contents.
4. Run bounded keyphrase extraction and single-hop synthesis through the selected generator. Check cancellation and current access during preparation and before each model dispatch.
5. Validate candidate structure, size limits, and source attribution. Persist usable candidates as **unreviewed** with provenance. Report invalid candidates, shortfalls, and unit failures separately.

The default request is **20 cases**, not a guarantee of 20 valid or distinct cases. A small corpus may supply fewer suitable passages. Avoid exact duplicates within the batch. Do not spend indefinitely regenerating to reach 20. Saved partial results remain reviewable.

<a id="use-an-explicit-minimal-preset"></a>

### Use an explicit minimal preset

Configure `SingleHopSpecificQuerySynthesizer` with keyphrases as its selected property, explicit personas, and explicit gateway-backed model bindings. A **persona** describes the reader whose questions are being proposed. The preset supplies a general reader persona unless the user supplies bounded domain guidance. Creating it must not invoke an undisclosed model.

Reuse Inframeld's processed text, not a second parser. This preset has **no additional generation-time embeddings and no relationship graph** linking passages. Ragas may hold passage nodes in memory. That does not introduce an application graph database or authorize its default graph-building transforms. Its default transform recipe does more work than this preset needs.

If a selected API requires an embedding object, bind a gateway adapter to the existing selected embedding connection rather than allowing a default client. The starter operation authorizes zero generation-time embedding calls: an unexpected call fails before dispatch, rather than spending outside the preset. Future embedding-assisted synthesis requires explicit model selection, disclosure, and budget.

The sample aims to cover several parts of the corpus. It is not statistically representative or certified ground truth. Automatic multi-hop and negative-case synthesis are deferred.

<a id="review-immutable-case-revisions"></a>

<a id="review"></a>

<a id="2-review-immutable-case-revisions"></a>

## Review immutable case revisions

Alice sees a question about young Rossum, a proposed answer, and its actual excerpt with surrounding text. She need not type a passage from memory or select character offsets in the terminal.

A **TestCase** has a stable identity in one pipeline. Its immutable **case revision** contains the question, reference, and expectation. Review decisions apply to an exact revision and record reviewer and time. [Evaluation records](records.md#evaluation) defines these logical records, not mandatory separate database tables.

| Action | Result |
| --- | --- |
| **Accept** | Record an explicit authorized review decision for this exact revision. Interactive review displays the question, proposed answer, and resolvable exact passage first. Acceptance is not a model score or proof of correctness. |
| **Edit** | Create a new unreviewed content revision, even if the previous revision was accepted. Preserve old benchmark memberships. |
| **Reject** | Mark this revision rejected and exclude it from new benchmark admission. Retain authorized history within retention. |
| **Later** | Leave the revision unreviewed and save review position. Do not accept or reject it. |
| **Remove** | Exclude the case from future benchmark selection without rewriting frozen snapshots. Removal is distinct from erasure. |
| **Finish review** | Save completed actions and return to the shell. Review can resume. Evaluation does not start. |

Record who reviewed the revision and whether that reviewer was a human or an application. A script must specify the exact revision and the review action. A general spending-confirmation flag does not accept a case, and an automated decision must never be labelled human review.

An application may accept an exact case revision when it has explicit permission to do so. It still needs current access to the expected evidence, and that evidence must remain resolvable. These checks apply even without an interactive screen. The [reviewed Access catalogue](../../inframeld-access-models/references/actions-and-initial-grants.md#reviewed-capability-catalogue) supplies `review-evaluation-cases` on the exact Pipeline, with human/application use eligibility for acceptance and rejection. Separate human-only [case-audience administration](case-audiences.md#case-audiences) and [fixed creator assignments](../../inframeld-access-models/references/actions-and-initial-grants.md#initial-assignments) are accepted. Exact public/physical schemas remain delivery work. Application eligibility alone grants nothing.

Editing generated cases is in scope. Manual authoring from a blank form is deferred. The initial expectation comes from generation. Any advanced evidence edit must select a resolvable source-backed passage through the application evidence contract, not substitute pasted text or a filename. It also creates an unreviewed revision. No terminal drag-selection interface is required for starter review.

The default regression benchmark selects the **current accepted revision of each active case**. After an accepted case is edited, that case is excluded from newly assembled default benchmarks until the new revision is accepted. Do not silently fall back to the old accepted revision. Existing frozen benchmarks remain unchanged and may be selected explicitly while their evidence remains available and permitted.

An explicit **exploratory** run may include unreviewed revisions. Label that fact and review states in admission, results, and exports. It does not promote their review state or constitute a reviewed regression benchmark. Rejected and removed cases are not silently restored.

<a id="failures-status-and-sources"></a>

## Failures, status and sources

Changed source bytes cannot retarget an expected passage silently. Missing mappings and unavailable execution inputs have different outcomes.

Current access is checked before model egress and later disclosure. Human/JSON progress shows actual counts and saved results without exposing protected case populations.

Ragas starter generation is the accepted choice under ADR-0051, superseding historical ADR-0030. Inspected library interfaces and a planned CLI journey do not establish an executed end-to-end integration or calibrated judge. Keep the historical first-use journey separate from delivered behavior.

- [Generation](#generation), [review](#review), [result presentation](metrics-and-evidence.md#result-presentation), [passages](passage-coverage.md#passages), [records](records.md#evaluation) and [V1 scope](../../inframeld-architecture/references/v1-scope-and-extension-boundaries.md).
- [ADR-0051](../../../../docs/adr/ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md) explains Ragas scope. [Onboarding](../../inframeld-architecture/references/first-use-and-private-defaults.md) owns optional first-use completion.
