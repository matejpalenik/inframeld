# ADR-0008: In-app pipeline evaluation and explicit release decisions

**Status:** Accepted — OpenEvals, a configurable Luna judge, and the in-app evaluation workflow. Implementation qualification is pending. **Date:** 17 September 2026. **Updated:** 19 September 2026. **Required approach:** Inframeld owns test cases, evaluation history, comparisons, and release decisions. Every model call uses `ModelGateway`; no hosted evaluation-platform account is required. **Source:** [Canonical architecture guide](../ARCHITECTURE.md). **Related:** [API contract](ADR-0002-product-owned-openapi-contract.md), [model gateway](ADR-0006-byok-provider-boundary.md), [release transitions](ADR-0009-sticky-logical-canary-deployments.md), [processing and reranking](ADR-0016-docling-processing-and-cross-encoder-reranking.md).

## Context

A pipeline retrieves document excerpts and uses them to generate an answer. Changing its prompt, retrieval settings, model, or source documents can improve some answers while making others worse.

An engineer needs to see those differences before deciding what to release. The useful workflow is to open a pipeline, maintain representative questions, run a baseline and candidate against the same questions, and inspect changed answers and evidence. An average score alone cannot explain which cases regressed or whether failures were excluded from the calculation.

From first principles, this requires three separate responsibilities: **execute the pipeline**, **evaluate the resulting observations**, and **decide whether to release a version**. A library can help with evaluation, but it does not supply Inframeld's permissions, immutable versions, test history, durable jobs, or release controls.

Evaluation and release management are core v1 capabilities. The initial goal is quick, useful feedback inside Inframeld—not a large evaluation suite, a generic experiment platform, or an autonomous optimizer.

## Decision

**Use OpenEvals's whole-answer groundedness judge, initially configured with GPT-5.6 Luna, alongside application-owned retrieval, citation, and outcome calculations. Run explicit comparisons inside Inframeld, preserve their exact inputs and results, and keep release authority separate from evaluation.**

A **judge** is a model used to assess another model's answer. **Groundedness**, also called **faithfulness** here, asks whether that answer is supported by the context supplied to it. It is not a general test of truth, relevance, or completeness.

The selected starting behavior is OpenEvals 0.2.0's groundedness prompt and single LLM-as-judge evaluator, returning a boolean verdict and explanation. The library and model are selected; their integration, rubric, edge cases, budgets, and numerical qualification criteria still need testing. The inspected package versions are not automatically final dependency pins.

Keep test cases, snapshots, runs, and results in the existing application database and artifact storage. Use the existing worker and Studio, Inframeld's web console. No additional Docker Compose evaluation service is needed.

OpenEvals is maintained in LangChain's repository under MIT. It depends on the LangSmith SDK, but LangSmith is a separate platform, not a prerequisite for this workflow. The recorded [OpenEvals repository and integration documentation](https://github.com/langchain-ai/openevals) distinguish the library from its optional platform integration. Tracing and export must be explicitly disabled and tested, as described below.

### 1. Let the engineer compare two ready versions inside Inframeld

A **baseline** is the version used as the reference. A **candidate** is the version being considered. A **benchmark** is the set of test cases used to evaluate them.

#### Maintain one benchmark per pipeline

The pipeline's Tests view supports creating, reading, editing, and removing cases. Each case contains a question and may also contain expected-source identities, an expected abstention, a reference answer, or notes.

An **expected abstention** identifies a case where the pipeline should decline to answer rather than supply an unsupported answer. A **reference answer** helps a human compare outputs; supplying one does not silently enable an answer-correctness judge.

Start with one benchmark per pipeline, not a separate dataset-management product.

#### Explicitly build, then compare

Build the candidate explicitly. Once it is ready, choose **Compare versions** and select the named baseline, candidate, and saved benchmark revision. Show the judge configuration, evaluation scope, and estimated budget before execution.

Saving or admitting the comparison freezes the benchmark if necessary. **Admission** means durably accepting the operation. Both runs bind to the same immutable snapshot: later edits cannot change the questions being executed.

A proposed quick preset contains **20–50 representative cases**. This is a feedback sample, not a claim of statistical sufficiency or a commercial limit.

#### Execute the same paths used for serving

The durable operation runs both exact versions through the normal authorized retrieval, reranking, generation, citation, and failure paths, then scores the results. A **reranker** reorders retrieved candidates before the final context is selected.

Reuse ready **materializations**, the prepared searchable indexes bound to those versions. Evaluation must not silently rebuild a corpus or choose newer documents. A corpus is the body of source documents used by the pipeline.

The worker continues after the browser closes. Reopening the page reads the recorded operation and run IDs rather than starting another comparison.

#### Show paired results and keep their history

For each case, display the baseline and candidate side by side: execution status, answer, citations/evidence, groundedness verdict and explanation, expected-source hit result, latency, and usage.

Highlight **supported-to-unsupported changes**, **source-hit losses**, and **new execution or judge failures** as distinct signals. A failed judge is not the same finding as an unsupported answer.

Keep history accessible from both the pipeline version and the stable test-case identity, with case and benchmark revisions visible. Editing or removing an active case does not rewrite past results. Studio and optional API automation use the same durable operations and result contract; neither requires an external runner, LangSmith, or Langfuse setup.

Release remains a separate authorized command. Saving a test, editing a pipeline, or completing a build does not automatically run the judge. A combined build-and-compare action is a possible later convenience, not required now.

#### Run both versions freshly in the initial workflow

Do not initially substitute a cached historical baseline for a fresh execution.

Later baseline reuse would require matching case/dataset semantics, pipeline, evaluator configuration, and effective authorization context. Its age and reuse must be visible, and permissions must be rechecked before reuse or disclosure. Matching IDs or fingerprints cannot prove that an external model alias still points to unchanged behavior.

### 2. Preserve history with a small application-owned model

A stable identity lets the user follow an item over time. An immutable revision records what that item contained for a particular evaluation. Both are needed: the same case can have a history without pretending its question never changed.

| Concept | Minimum responsibility |
| --- | --- |
| **Test case** | A stable ID associated with one pipeline, its active/removed state, and its current case revision. Use this identity to browse history. |
| **Case revision** | The immutable question, expected-source labels, expected-abstention setting where supplied, and optional reference answer/notes. Editing produces a new revision; old runs retain their original input. |
| **Benchmark revision** | An immutable, ordered snapshot of case IDs and exact case content/revisions. Save it explicitly or freeze it at comparison admission. Both runs use it. |
| **Evaluator revision** | The immutable scoring contract: library/version, prompt/rubric and schema hashes, metric definitions, judge alias/configuration revision, and generation settings. |
| **Evaluation run** | One pipeline version, benchmark revision, evaluator revision, initiating actor and effective authorization scope, durable job status, timestamps, and summary counts. A comparison references two runs. |
| **Case result** | Run and case-revision identities; execution and per-metric statuses; scores/reasons; answer and evidence artifact references; observed pipeline/model identities; durations and usage. Include failed and unattempted cases. |

A **rubric** is the set of rules the judge applies. A **schema** defines the required response structure. The initiating **actor** is the verified human or application requesting the run; effective scope records what that actor may access for the evaluation.

These concepts do not require a class hierarchy, a repository/table per concept, or a generic versioning framework. Stable case IDs and an immutable full benchmark snapshot are enough initially. A case revision can be identified by its snapshot content or hash rather than a separate aggregate. The evaluator revision can be a saved configuration record, not a plugin registry. A comparison does not need another execution engine.

#### Do not replace earlier observations with later results

Finalize observations without overwriting them during another run. Retries follow the job/idempotency rules and retain attempt history. They must not quietly replace one judgment with a more favorable one.

A removed case remains identifiable in authorized history until its retention expires. Explicit erasure overrides retained content: report that evidence is unavailable rather than claim full reproducibility after deletion.

A changed question or expected meaning is a different benchmark input even when the stable case ID is unchanged. Compare both versions against the same newly frozen benchmark, or explicitly select an unchanged subset and show its coverage. Do not present different case revisions as an identical regression test.

### 3. Report separate metrics with explicit denominators

Faithfulness, retrieval, and citation checks are required in v1. The following are the **proposed minimal calculation definitions**, whose edge cases still need qualification.

Return counts, applicability, and failures alongside scores. A zero denominator produces **`not_applicable`**, not an invented zero or perfect score.

| Signal | Proposed calculation | What it does not establish |
| --- | --- | --- |
| **Faithfulness / groundedness** | For each applicable answer, obtain a boolean support verdict and explanation. Aggregate supported answers divided by successfully judged applicable answers. Also show eligible, failed, and skipped counts. | Not a percentage of extracted claims, a confidence score, or proof of truth. |
| **Expected-source hit rate at k** | Cases with at least one expected source among the first **k final evidence chunks**, divided by successfully scored cases with a nonempty expected-source set. Deduplicate source identities and show failed/unscored eligible cases separately. | Measures evidence discovery, not semantic correctness. Several expected sources still contribute at most one hit for a case. |
| **Citation presence and validity** | Answered cases with at least one valid backend-derived citation divided by answered cases. Count invalid citations separately. A valid identity resolves to that version's permitted evidence. | A citation's presence and valid identity do not prove that it supports every claim in the answer. |
| **Answer, insufficient-evidence, and execution outcomes** | Count outcomes across all admitted cases, including failed, cancelled, and unattempted cases. Report execution failures divided by attempted cases as a separate rate. | An answer is not automatically correct; abstention is not automatically wrong. |
| **Latency and usage** | Record per-case query duration and p50/p95 with sample counts for completed answers and abstentions. Report gateway calls, tokens, and cost; show failures/timeouts, judge time, and total time including queueing separately. | Small-sample percentiles describe those observations, not a reliable production distribution. Unknown token/cost data are unknown, not zero. |

Here **k** is the number of final evidence chunks considered. A chunk is a retrieved source excerpt. **p50** is the median observed duration; **p95** is the 95th percentile. Always show how many observations contributed.

Expected-source labels must declare whether they identify a **logical document**, which can have several versions, or one **exact document version**. That distinction matters when comparing a deliberate source update.

The application-owned arithmetic adds no model calls. Executing each pipeline still incurs its configured generation, query-embedding, and other model operations. An embedding is a numerical representation used for similarity search.

A later **source recall at k** metric could measure how many required sources were found: distinct expected sources retrieved divided by expected sources for each case. Keep its name distinct from hit rate, which asks only whether at least one was found.

**No blended quality score is needed in v1.** A reference answer also does not make substring matching a valid correctness test.

### 4. Interpret groundedness according to the recorded rubric

The selected OpenEvals 0.2.0 `RAG_GROUNDEDNESS_PROMPT` compares the **answer with `context`**. It does not use the question or a reference answer.

The rubric treats unsupported additions, contradictions, and invalid inferences as problems, while allowing basic facts such as arithmetic. It is therefore not strict proof that every statement follows exclusively from the corpus. Pin or hash the prompt, and record a policy change as a new evaluator revision.

This is a **whole-answer judgment**, not a claim-extraction pipeline. The library does not return a structured list of claims, per-claim source attribution, or a reliable classification of failure causes.

#### Judge the context the generation model actually received

Use the exact authorized final context supplied to generation **after reranking and truncation**. Adding other documents or including discarded chunks changes what is being assessed.

Show the original answer, context identities, and explanation so an engineer can inspect the result. A short, irrelevant answer can still be grounded. This metric does not establish completeness, relevance, or whether the underlying source is true.

#### Keep missing evidence and judge failures distinct from negative verdicts

| Situation | Required treatment |
| --- | --- |
| **Explicit pipeline abstention** | Groundedness is `not_applicable`; the abstention remains visible in outcome counts. |
| **An answer appears to contain no factual claims** | Do not automatically infer a special claim-free category or give it a perfect score. |
| **Answered case with no usable bound evidence** | Record a visible input/missing-evidence failure. |
| **Valid boolean verdict that the answer is unsupported** | Record an unsupported judgment, not an execution failure. |
| **Judge refusal, malformed/truncated output, or missing verdict** | Record a judge failure, not an unsupported-answer judgment. |
| **A string such as `"false"` instead of a boolean** | Reject it. Accept only an actual boolean and a bounded explanation; do not coerce a string into a passing verdict. |

Answers and excerpts are untrusted data. The judge receives no tools, arbitrary endpoints, or release authority. Schema validation can check response shape; it cannot prove semantic correctness or immunity to prompt injection. Include adversarial excerpts in calibration.

Evaluation content follows normal authorization, data-egress, and retention rules. **It is retained evaluation evidence, not ordinary operational-log content.**

### 5. Integrate OpenEvals through ModelGateway, not another provider client

`ModelGateway` is the application's existing interface for model calls. An adapter translates between that interface and a library's expectations without giving the library a competing model configuration system.

```text
Authorized comparison from Studio or an optional API client
    -> Freeze benchmark/evaluator revisions and admit durable runs
        -> Execute baseline and candidate through serving paths
            -> ModelGateway for their model calls
        -> Calculate retrieval, citation, and outcome signals
        -> Run the OpenEvals asynchronous groundedness evaluator
            -> In-process ModelClient facade
                -> ModelGateway bound to this authorized run
        -> Persist Inframeld case results, comparison, and history

A release decision is a separate authorized command.
```

Use `create_async_llm_as_judge` with the released groundedness prompt and an explicit `judge` implementing OpenEvals's structural `ModelClient` shape: **`chat.completions.create`**.

This **facade** is an in-process wrapper around `ModelGateway`, not an OpenAI SDK client or another router. If a synchronous path is exposed, it must have the same guarantee. Return the small response shape the library reads, then translate results into Inframeld-owned **DTOs**, or data transfer objects. Domain code must not depend on OpenEvals or LangChain types.

#### Validate the actual direct-client response

The recorded inspection of the released `openevals/llm.py` direct-client path found one call to `chat.completions.create`, supplying messages, model, and a strict JSON-schema response format. It then parses `choices[0].message.content`.

The default schema requires boolean **`score`** and, with **`use_reasoning=True`**, string **`reasoning`**. That flag asks the evaluator to return an explanation. **It is not the model provider's reasoning-effort setting.**

The inspected path has no retry or schema-repair loop. Plain `json.loads` only parses JSON; validate the exact response shape, actual boolean type, bounded explanation, and successful completion before accepting a result.

The recorded source is the [exact OpenEvals 0.2.0 wheel](https://files.pythonhosted.org/packages/4a/8b/00f402b7f3475e235c339a9bc82d2eaf46cc08b53ecd85d4a117850170d3/openevals-0.2.0-py3-none-any.whl), including `llm.py`, `types.py`, `utils.py`, and `prompts/rag/groundedness.py`.

#### Bind the library to the admitted run

Bind the facade to the run's authorized connection, model alias, and immutable settings. Validate the library's model argument against that binding. Inject the authorized output-token limit, provider reasoning setting, deadline, budget, and correlation IDs through `ModelGateway`. Correlation IDs link calls to their originating operation.

Do not supply independent endpoint credentials or invoke the library with **`judge=None`**, which would initialize its own model. Provider-specific schema translation belongs in the gateway adapter.

A private gateway must demonstrate that it supports the required structured-output subset. A provider model's advertised capability does not prove that an intervening gateway forwards it correctly. The recorded reference is [structured-output requirements and refusals](https://developers.openai.com/api/docs/guides/structured-outputs).

#### Disable tracing and export explicitly

OpenEvals wraps scoring with LangSmith tracing and adds feedback logging inside a LangSmith testing context. Set tracing off at worker initialization and execute this adapter inside **`tracing_context(enabled=False)`**.

Do not run it under LangSmith test/experiment tracking or supply LangSmith credentials or export clients. Neither absent keys nor a library's “standalone” description proves there is no outbound tracing.

The inspected direct-client trace metadata hard-codes an OpenAI provider label. **Authoritative provider/model provenance comes from `ModelGateway`, not that label.** Verify the locked SDK's actual network behavior. The recorded reference is [LangSmith's explicit tracing controls](https://docs.langchain.com/langsmith/trace-without-env-vars).

### 6. Enforce one authorization, budget, and retry policy for evaluation

Every model call must traverse the scoped `ModelGateway`: pipeline generation, judging, and any future claim extraction, scoring embeddings, schema repair, or nested judge. Preserving that rule does not add those deferred operations to v1.

| Boundary | Required behavior and qualification |
| --- | --- |
| **Model-call routing** | Exercise every exposed synchronous/asynchronous path through a recording gateway. No framework receives provider keys. Integration tests block other network destinations, including telemetry and export endpoints. |
| **Whole-run resource limits** | Bound cases, concurrency, deadlines, tokens, and model calls across the complete run. Any later permitted repair consumes the same budget and is recorded. |
| **Retries** | The gateway owns retry policy. Framework/SDK retries must not multiply it. Ambiguous provider outcomes follow ADR-0007, not a silent replay of the evaluation. |
| **Authorization and configuration** | Fail closed when authorization, connection, alias, required capability, or a valid response is missing. Fail closed means deny or fail the operation rather than continue with a weaker substitute. |
| **Provider and context behavior** | A provider refusal/error is an execution failure, not a quality verdict. No hidden model/provider fallback or silent judge-context truncation is allowed. |
| **Evidence and logging** | Preserve provenance and authorized evidence without credentials. Keep prompts, excerpts, and full answers out of ordinary logs. |
| **Measured behavior** | Measure actual calls, elapsed time, and dependency impact before declaring the integration qualified. |

An **ambiguous provider outcome** means a request may have executed even though its response was lost. Repeating the whole evaluation could repeat chargeable work; the durable-job policy handles that uncertainty.

These are implementation tests still to perform. **No framework, gateway adapter, or judge model was executed in the documentation research recorded by this ADR.**

### 7. Keep the initial judge configurable and its cost visible

The application evaluation alias initially resolves to **`gpt-5.6-luna`**. The starting judge remains replaceable through the same application alias system, including authorized private or local gateways. OSS operation does not require an OpenAI account.

For qualification, the recommended configuration is explicit provider reasoning effort **`none`**, strict structured output, and a bounded explanation/output budget. These are trial settings; record adjustments as a new evaluator revision.

The model documentation recorded with this decision lists structured outputs, Chat Completions, and the `none` reasoning option. Do not assume the default reasoning setting is `none`. The inspected page exposed an alias without a separate dated snapshot: record resolved identity where available and recheck alias drift.

#### Recorded pricing basis, not a live price guarantee

The source records these ordinary short-context rates on **19 September 2026**, in US dollars per one million tokens:

| Model            | Uncached input | Output |
| ---------------- | -------------: | -----: |
| **GPT-5.6 Luna** |          $0.20 |  $1.20 |
| **GPT-5.4 mini** |          $0.75 |  $4.50 |

At those recorded rates, Luna is about **73.3% lower** for both categories. This meets the price condition used to select the initial judge; it is not a quality test.

The rates exclude gateway markups, service-tier/regional differences, and long-context pricing changes. Recorded references: [Luna model and pricing](https://developers.openai.com/api/docs/models/gpt-5.6-luna), [mini model and pricing](https://developers.openai.com/api/docs/models/gpt-5.4-mini), and [pricing details](https://developers.openai.com/api/docs/pricing).

#### Separate judge cost from the two pipeline executions

For **50 cases answered and successfully judged on each of two versions**, OpenEvals makes **100 nominal judge calls**. Under the historically inspected alternatives, Ragas would make 200; DeepEval would make 300 without its summary reason or 400 with its default reason. Call counts do not imply equal token consumption or equivalent metrics.

Using an illustrative **single-call** budget of 6,000 uncached input tokens and 1,000 billed output tokens:

```text
Luna judge cost per answer
    = (6,000 / 1,000,000 × $0.20) + (1,000 / 1,000,000 × $1.20)
    = $0.0024

100 judged answers × $0.0024 = $0.24
```

This is arithmetic using the recorded prices, not measured usage or a price promise. It excludes both pipeline executions, retries, optional repair, and repeated calibration.

Expose gateway-reported usage, including billable reasoning tokens. If a customer gateway cannot report cost, say that the cost is unknown.

**The initial judge choice never authorizes automatic fallback** to mini, a stronger model, or an ensemble of models. If qualification fails, report the failure and explicitly revisit the selection rather than weaken the metric or silently change provider.

### 8. Retain enough evidence to inspect a result, within declared bounds

Each run binds to the ordered case revisions, pipeline/corpus versions, processing and embedding profiles, ready materializations, retrieval/reranker/generation settings, and effective principal/authorization scope and revision. A **principal** is the stable human or application identity recognized by Inframeld.

Retain the exact bounded final context supplied to generation, or an immutable authorized artifact that can reconstruct it. Include chunk and document-version identities and their order. **A hash alone cannot support later inspection after the source content disappears.**

The evidence also records the final answer and citations, outcome, selected retrieval/rerank observations, evaluator revision, judge verdict and explanation, gateway call IDs, observed model identity, and usage.

Keep intermediate retrieval identities and scores only within a declared bound. Full vector dumps and unlimited traces are unnecessary.

#### Preserve useful evidence without promising complete diagnosis

These observations can support investigation of retrieval misses, changed ranking/context, unsupported answer additions, or judge disagreement. They are not a complete execution replay and do not guarantee that every historical root cause can be determined.

Keep the existing evaluator boundary and the versioned evidence-read DTO used by case-detail/history views application-owned. A future diagnostic component could consume those observations and propose explanations or remedies without rewriting history.

Its detailed interface and implementation are deferred. Do not add an empty diagnostic port now or allow evaluation to change pipeline configuration automatically.

### 9. Compare only cases that are meaningfully comparable

**A run can finish while its comparison remains inconclusive.** Execution status describes whether the work completed. Comparison sufficiency describes whether the retained, compatible evidence supports a conclusion.

Preserve partial results, per-metric failures, and applicability. Calculate paired changes only for cases successfully and compatibly scored on both sides. Show the paired count against the eligible count and each version's failures or missing evidence.

**Never claim an improvement by dropping failed candidate cases from view.**

| Comparison type | Required interpretation |
| --- | --- |
| **Same-corpus comparison** | Benchmark/case semantics and evaluator revision match, corpus revisions match, and permitted document scope is equivalent. Declare the pipeline configuration changes being evaluated. |
| **Corpus-change comparison** | Source revisions intentionally differ under the same benchmark and intended labels. Declare that change. Logical-document labels may survive the update; missing exact-version labels remain visible mismatches. |
| **Incompatible comparison** | Changed questions/expected meaning, metric definitions, or unsupported differences in authorization scope prevent a like-for-like improvement claim. |

An unchanged-case subset across benchmark revisions can still be useful when scoring definitions and effective scope match. Show the exclusions and coverage. Selecting unchanged questions does not make two different rubrics comparable: **rerun both pipeline versions under one evaluator**.

Results describe the recorded access scope. An engineer or service with broad permissions does not establish behavior for every integration credential with narrower document access.

Recheck current permission before showing or exporting retained content. A historical scope fingerprint records past execution; it does not grant permission now.

### 10. Calibrate the selected judge during implementation

**Calibration** checks the selected judge against a small set of human-reviewed examples under the intended rubric. It is a qualification exercise, not a second model's opinion treated as ground truth.

Within the proposed 20–50 representative questions, manually label a bounded subset such as **10–15 answers** against their exact supplied contexts. Label the whole-answer groundedness outcome and note the particular unsupported or contradicted statements.

Include supported answers, unsupported additions, changed numbers, negation, mixed supported/unsupported content, basic arithmetic, abstention, long evidence, and prompt-injection attempts. Reserve several cases from prompt/configuration tuning. Mark disputed human labels and show their exclusion until they are resolved.

#### Measure errors as well as agreement

Measure agreement on undisputed applicable cases, false passes among human-labelled unsupported answers, structured-output failures, model-call counts, tokens, elapsed time, and cost. A **false pass** means the judge accepts an answer the human label identifies as unsupported.

The proposed initial criteria remain open for agreement:

| Proposed criterion | Interpretation |
| --- | --- |
| **At least 90% whole-answer agreement** | Report the numerator and denominator on the labelled sample. This is not a production-accuracy estimate. |
| **No false pass on deliberately seeded critical contradictions** | Test the chosen critical examples explicitly; do not hide a miss inside an aggregate. |
| **All invalid outputs and failures remain visible** | Output failures are not discarded or converted into quality verdicts. |

These small-sample checks are not automatic deployment gates. Claim-extraction coverage is relevant only if a claim-extracting metric is later selected; it is not a requirement of this whole-answer judge.

#### Check repeatability without selecting favorable results

Run **five fixed borderline/adversarial examples three times each** with unchanged settings. Preserve every observation and report verdict changes and explanation changes.

Differences comparable to the observed variation are inconclusive. Fixed settings, deterministic arithmetic, and temperature zero do not make model observations deterministic.

Recalibrate after changes to the library, prompt, model, gateway capability, or material language/corpus characteristics. Start with the selected Luna judge. Comparing a different model is an explicit later decision if these checks fail, not an automatic fallback.

### 11. Keep release authority independent of evaluation

Evaluation is advisory. Neither an evaluator nor a completion webhook changes Deployment pointers—the references that select which version serves requests.

| Publication mode | Who authorizes publication | How comparison behaves |
| --- | --- | --- |
| **Manual releases** | An engineer explicitly requests the release in Inframeld, or an authorized API client invokes the same application operation. | Results inform that decision; they do not make it. |
| **Automatic updates** | The authorized source/configuration action described in ADR-0019 supplies publication authority independently of evaluation. | Comparisons remain explicit and bind exact versions. Starting one does not pause automatic publication. |

Manual release commands check permission, readiness, idempotency, and the expected revision. **Idempotency** prevents duplicate execution of the same request; an **expected revision** protects against overwriting a concurrent change.

Record the actor and actor type, evaluation reference, and acknowledgment of missing, failed, inconclusive, or regressed evidence. An optional rationale has a defined size bound. Human identity and service credentials follow ADR-0005; an external CI service is not required to own the decision.

Automatic updates do not run a judge or fabricate an approved benchmark. **Switch to Manual releases when the serving endpoint must stay fixed during review.** A completed comparison never changes publication mode or selects a release target.

### 12. Leave deeper evaluation and platform integration outside v1

The in-app workflow, immutable snapshots, fresh baseline/candidate execution, case results, and history are already decided. They do not wait on another library comparison. Reopen the selected library only for a concrete blocker.

Deeper diagnosis/remediation, customer-defined rubrics/evaluators, broader correctness/relevance judges, generated datasets, generic experiment services, model ensembles, and autonomous remediation or promotion remain deferred. So do claim extraction and claim-percentage scoring: they were earlier recommendations, not product requirements.

#### Preserve an exportable evidence boundary without building an exporter

LangSmith, Langfuse, and exporters are outside v1. Keep internal benchmark, case, run, pipeline, and evaluator IDs authoritative. Optional namespaced external references can identify a corresponding item in another system without replacing those identities.

A future export adapter could map an authorized, versioned evidence DTO into external datasets, experiments, scores, or traces. Its exact interface and content/retention policy remain undecided. Do not store LangSmith/Langfuse SDK objects in domain records, promise automatic round-trip synchronization, or add an unused export service now.

Export failure must not change an evaluation or release result. Exporting must not rerun a judge.

#### Recorded platform capabilities are future integration evidence

The source's recorded platform research describes LangSmith uploads of externally run experiments using **external dataset identities**, per-row outputs/scores, and comparison views. This is not an API for appending to any arbitrary native dataset. References: [external experiment upload](https://docs.langchain.com/langsmith/upload-existing-experiments) and [comparison views](https://docs.langchain.com/langsmith/compare-experiment-results).

The same research describes Langfuse experiment comparison, externally computed scores, and SDK/OpenTelemetry ingestion. OpenTelemetry, often abbreviated OTEL, is the telemetry interface referenced by that integration. The inspected documentation did not provide a generic public REST experiment-create endpoint. References: [Langfuse comparison](https://langfuse.com/docs/evaluation/experiments/compare-experiments) and [OpenTelemetry experiments](https://langfuse.com/docs/evaluation/experiments/experiments-via-opentelemetry).

Both are possible later consumers of Inframeld evidence, not prerequisites for its screens. Keep judge execution inside Inframeld through `ModelGateway`. Another platform's custom gateway URL does not establish the same authorization, budgets, or attribution; external execution would require separate qualification.

The recorded licensing distinction also matters: OpenEvals's MIT license and LangSmith's SDK license do not make the LangSmith platform open-source. Its self-hosted offering requires an enterprise license. Langfuse's core has MIT terms with separately licensed EE directories. References: [LangSmith self-hosting](https://docs.langchain.com/langsmith/self-hosted), [Langfuse model connections](https://langfuse.com/docs/administration/llm-connection), and the [recorded Langfuse v4.38.0 license](https://raw.githubusercontent.com/langfuse/langfuse/v4.38.0/LICENSE).

**No hosted account or additional evaluation platform belongs in the MVP Compose baseline.**

## Consequences

### Positive

- **Engineers can inspect changes where they manage the pipeline.** Tests, paired answers, regressions, and case/version history stay inside Inframeld rather than depend on an external runner or platform.
- **The initial judge has a narrow responsibility.** A maintained whole-answer evaluator supplies a boolean verdict and explanation with one nominal judge call; native calculations provide separate retrieval, citation, and outcome signals without a custom metric framework.
- **Evidence does not become release authority.** Immutable snapshots preserve what was evaluated, current access protects retained content, and the shared gateway enforces model-call policy. Evaluation cannot silently release a version or change its configuration.

### Negative

- **Inframeld still owns most of the product workflow.** The library does not implement case management, snapshots, jobs, authorization, evidence storage, comparisons, or release controls. Its dependencies and gateway integration also need qualification.
- **A groundedness result has limited meaning and can vary.** A boolean judgment does not measure claim coverage, completeness, relevance, or source truth. Failures, changed inputs, and small samples can leave a comparison inconclusive.
- **Useful evaluation costs execution and storage.** Freshly running both versions, judging applicable answers, and retaining bounded answers/context consume resources. Budgets, privacy controls, retention, and unknown provider usage must stay visible.

## Alternatives considered

### Basis of the recorded comparison

The source records inspection of PyPI metadata and exact released wheels on **19 September 2026**, without installing or executing them:

| Package | Inspected release | Recorded release date |
| --- | --- | --- |
| **OpenEvals** | [0.2.0 metadata](https://pypi.org/pypi/openevals/0.2.0/json) | 7 April 2026 |
| **Ragas** | [0.4.3 metadata](https://pypi.org/pypi/ragas/0.4.3/json) | 13 January 2026 |
| **DeepEval** | [4.2.3 metadata](https://pypi.org/pypi/deepeval/4.2.3/json) | 14 September 2026 |

These are research versions, not automatically accepted dependency pins. OpenEvals's inspected main branch reported 0.2.1; the behavior described here comes from the published 0.2.0 wheel.

Dependency observations came from package metadata. They are not image-size, import-time, memory, or latency benchmarks. Release age and package count do not establish comparative maturity or accuracy, and these metrics do not measure exactly the same thing.

### OpenEvals groundedness — selected

The nominal successful path uses **one judge call**, normally returning a boolean score and explanation, with no scoring embeddings.

This fits the initial case-level comparison without introducing claim extraction. Explicit dependencies include LangChain, LangChain OpenAI, LangSmith, and Rich; it is not dependency-free. The integration still needs the gateway facade, response validation, and disabled tracing/export described above.

The selection reduces required adapter work for the initial product. It is not a measured accuracy or performance ranking. Its single boolean must not be displayed as a claim-support percentage.

### Ragas claim-based faithfulness

**Not selected for v1.** The inspected `metrics.collections.Faithfulness` path uses **two sequential calls**: extract answer claims, then judge their support against the supplied raw contexts. It adds no scoring embeddings.

Its supported/extracted-claim calculation provides an inspectable claim denominator, useful for finer diagnostics. Base dependencies include datasets, Instructor, and LangChain. The public result is a score; capturing typed intermediate evidence and validating complete claim correspondence add adapter work.

The recorded release returns **NaN**, or “not a number,” when there are no statements or verdicts. Its verdict schema permits arbitrary integers, so any selected adapter would need to enforce **0/1** and complete correspondence between extracted claims and verdicts. References: [released metric](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/collections/faithfulness/metric.py) and [released schemas](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/metrics/collections/faithfulness/util.py).

The historical integration assessment—not v1 implementation work—uses `InstructorBaseRagasLLM.generate(prompt, response_model)` and `agenerate(prompt, response_model)` through `ModelGateway`. It captures both typed responses in a per-case adapter, avoids provider factories and the full dataset runner, and sets **`RAGAS_DO_NOT_TRACK=true`** before initialization. Future scoring embeddings would also need a gateway-backed interface. References: [released LLM interface](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/llms/base.py) and [analytics source](https://github.com/vibrantlabsai/ragas/blob/v0.4.3/src/ragas/_analytics.py).

### DeepEval faithfulness

**Not selected for v1.** The inspected path extracts context truths and answer claims, then produces verdicts. It uses **three calls with `include_reason=False`**, or **four by default** with a summary reason. The first two extractions can run concurrently; it adds no scoring embeddings.

Broader test/assertion tooling does not replace Inframeld's screens or history. Dependencies include pytest plugins, OpenTelemetry, and telemetry packages. The context-distillation step and additional integration policy increase the work to qualify this one metric.

The recorded semantics normally count **`idk` as faithful** and return **1 when there are no verdicts**. Changing that ambiguity handling would be a recorded rubric choice, not merely an adapter detail. References: [faithfulness semantics](https://deepeval.com/docs/metrics-faithfulness) and the [exact inspected 4.2.3 wheel](https://files.pythonhosted.org/packages/cb/bd/72d116cc6e0b0ee247709a6c49c454008d7a7016046670f1fbee4117cf9a/deepeval-4.2.3-py3-none-any.whl).

The historical integration assessment requires a gateway-backed `DeepEvalBaseLLM`, including synchronous/asynchronous generation and schema methods. Override **`generate_with_schema` / `a_generate_with_schema`**: the inspected base catches `TypeError` and retries without a schema, which could cause an unintended second call.

It would also require disabling telemetry, dotenv loading, Confident AI exports, and optional tracing, then qualifying every wrapper and future embedding method. Dotenv loading reads environment settings from a file; it must not introduce another configuration path here. References: [custom LLM interface](https://deepeval.com/guides/guides-using-custom-llms) and [environment settings](https://deepeval.com/docs/environment-variables).

These integrations are feasible directions recorded for alternatives, not reasons to add another model configuration system or implement either library in v1.

### Build a custom native judge

**Not selected by default.** A native implementation could make one whole-answer call or several claim-level calls with the fewest library dependencies. Inframeld would then own prompt maintenance and metric evolution.

The selected direction prefers a maintained library. Reconsider a custom judge only if library qualification fails, rather than reopen the comparison without a concrete blocker.

## References

| Reference | Responsibility |
| --- | --- |
| [Canonical architecture guide](../ARCHITECTURE.md) | Overall product workflow and application ownership. |
| [ADR-0002](ADR-0002-product-owned-openapi-contract.md) | Application API and in-app comparison/release workflow. |
| ADR-0005 | Human identity, service credentials, and current authorization. |
| [ADR-0006](ADR-0006-byok-provider-boundary.md) | `ModelGateway`, configured customer/private endpoints, and model-call policy. |
| ADR-0007 | Durable jobs, idempotency, retries, and ambiguous provider outcomes. |
| [ADR-0009](ADR-0009-sticky-logical-canary-deployments.md) | Authorized release transitions and serving pointers. |
| [ADR-0016](ADR-0016-docling-processing-and-cross-encoder-reranking.md) | Processing and reranking behavior used by evaluated pipelines. |
| ADR-0019 | Automatic updates, Manual releases, and independent publication authority. |
