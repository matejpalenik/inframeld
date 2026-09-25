# Comparing pipeline versions with useful evidence

Alice wants to know whether Support's new version P13 handles her important questions better than P12. She compares both against the same saved **benchmark**, a fixed set of test cases. This guide explains what that comparison measures and what conclusions it can support.

Both versions use the normal [serving flow](pipelines-and-releases.md#serving). The [Evaluation records](data-model.md#evaluation) define cases, revisions, runs, and comparisons. Production feedback has a separate purpose and is not this benchmark.

Follow one comparison first, then read the metric definitions. Later sections explain the model judge, cost limits, retained history, and the tests needed before relying on results.

> **Design status:** The evaluation approach is accepted. Metric edge cases, judge integration, calibration, and implementation still need the verification described below. Proposed thresholds are not measured results or release gates.

## Contents

| Reader’s question | Start here |
| --- | --- |
| What exactly is compared? | [1. Freeze and execute a comparison](#comparison) |
| What do the scores establish? | [2. Read each metric separately](#metrics) |
| Which component calls the judge? | [3. Keep judging inside the model boundary](#gateway) |
| What work can a comparison charge for? | [4. Choose explicit settings and bound cost](#cost) |
| Can an old result still be inspected? | [5. Retain evidence and compare fairly](#history) |
| Which results remain unverified? | [6. Calibrate before relying on the judge](#qualification) |
| Can a score publish a version? | [7. Keep evidence separate from authority](#release) |
| What must a comparison make visible? | [8. Maintainer checks](#maintainer-checks) |
| Why these choices, and what remains open? | [9. Decision and reference map](#decision-map) |

<a id="comparison"></a>

## 1. Freeze and execute a comparison

P12 is the **baseline**, the version used for comparison. P13 is the **candidate**, the proposed replacement. Both answer the benchmark's cases.

### Maintain one benchmark per pipeline

The Pipeline's Tests view lets Alice create, read, edit, and remove cases. Each has a question and optional expected sources, expected abstention, reference answer, and notes.

An **expected abstention** means the pipeline should say it lacks evidence rather than invent an answer. A reference answer helps a person inspect the result. Adding one does not enable another correctness judge automatically.

Start with one benchmark per pipeline, not a separate dataset-management product.

### Explicitly build, then compare

Build P13 explicitly. Once ready, choose Compare versions and select P12, P13, and the saved benchmark revision. Show the judge settings, permitted evaluation scope, and estimated budget before starting.

Save or freeze the benchmark when the comparison is accepted. This saved acceptance is called **admission**. Both runs use the same fixed snapshot, so Alice's later test edits cannot change questions already queued.

A proposed quick preset contains **20–50 representative cases**. That is a useful starting sample, not a claim of statistical sufficiency or a product limit.

### Execute the same paths used for serving

The saved operation runs both exact versions afresh through normal permission checks, search, reranking, generation, citations, and failures. It then scores the results. Reranking reorders retrieved excerpts before the final evidence is chosen.

Reuse the versions' ready materializations, their prepared search data. Do not rebuild the corpus or substitute newer documents silently. The corpus is the selected set of sources.

The worker continues if Alice closes the browser. Reopening Studio finds the existing operation and run IDs instead of starting another paid comparison.

### Show paired results and keep their history

For each case, display the baseline and candidate side by side: execution status, answer, citations/evidence, groundedness verdict and explanation, expected-source hit result, latency, and usage.

Show a previously supported answer becoming unsupported, a lost expected source, and a new execution or judge failure separately. A judge that failed to respond has not judged the answer unsupported.

History is reachable from a PipelineVersion and from each case's stable ID, with case and benchmark revisions visible. Editing or removing a case leaves its past results intact. Studio and API automation use the same saved operations. Neither needs an external runner, LangSmith, or Langfuse.

Release is a separate authorized decision. Saving tests, editing settings, and finishing builds do not secretly run the judge. A combined build-and-compare action could be added later, but is not required.

### Run both versions freshly in the initial workflow

Do not initially substitute a cached historical baseline for a fresh execution.

Reusing an old baseline later would require matching case meaning, pipeline, evaluator settings, and effective access. Its age and reuse must be visible, with current permission checked before reuse or display. Even matching IDs or hashes cannot prove an external model alias still refers to unchanged behavior.

<a id="metrics"></a>

## 2. Read each metric separately

V1 requires faithfulness, retrieval, and citation checks. The table gives their proposed minimum calculations. Edge cases still need testing.

Show counts, cases where a metric applies, and failures alongside each score. With no eligible denominator, return `not_applicable`, not zero or a perfect score.

| Signal | Proposed calculation | What it does not establish |
| --- | --- | --- |
| **Faithfulness / groundedness** | For each applicable answer, obtain a boolean support verdict and explanation. Aggregate supported answers divided by successfully judged applicable answers. Also show eligible, failed, and skipped counts. | Not a percentage of extracted claims, a confidence score, or proof of truth. |
| **Expected-source hit rate at k** | Cases with at least one expected source among the first **k final evidence chunks**, divided by successfully scored cases with a nonempty expected-source set. Deduplicate source identities and show failed/unscored eligible cases separately. | Measures evidence discovery, not semantic correctness. Several expected sources still contribute at most one hit for a case. |
| **Citation presence and validity** | Answered cases with at least one valid backend-derived citation divided by answered cases. Count invalid citations separately. A valid identity resolves to that version's permitted evidence. | A citation's presence and valid identity do not prove that it supports every claim in the answer. |
| **Answer, insufficient-evidence, and execution outcomes** | Count outcomes across all admitted cases, including failed, cancelled, and unattempted cases. Report execution failures divided by attempted cases as a separate rate. | An answer is not automatically correct. Abstention is not automatically wrong. |
| **Latency and usage** | Record per-case query duration and p50/p95 with sample counts for completed answers and abstentions. Report gateway calls, tokens, and cost. Show failures/timeouts, judge time, and total time including queueing separately. | Small-sample percentiles describe those observations, not a reliable production distribution. Unknown token/cost data are unknown, not zero. |

Here, **k** counts final evidence chunks, which are source excerpts. **p50** is the median duration and **p95** the 95th percentile. Show how many observations contributed to either number.

Expected-source labels must say whether they name a logical Document or an exact DocumentVersion. A deliberate source replacement may preserve the Document while changing its version, so the labels affect how the comparison is interpreted.

Calculating these counts adds no model calls. Running the pipelines still uses their configured generation, question-embedding, and other model operations. Embeddings are the numerical representations used for search.

A later source-recall-at-k metric could count the fraction of expected sources found for each case. Keep that name distinct from hit rate, which only asks whether at least one expected source was found.

**No blended quality score is needed in v1.** A reference answer also does not make substring matching a valid correctness test.

### Interpret groundedness according to the recorded rubric

The selected OpenEvals 0.2.0 `RAG_GROUNDEDNESS_PROMPT` compares the answer with `context`, the supplied evidence. It uses neither the question nor a reference answer.

Its rubric flags unsupported additions, contradictions, and invalid inferences, while permitting basic facts such as arithmetic. It therefore does not prove that every sentence comes exclusively from the corpus. Pin or hash the prompt. A changed rubric needs a new evaluator revision.

The judge assesses the whole answer. It does not extract a structured list of claims, link every claim to sources, or reliably classify root causes.

### Judge the context the generation model actually received

Judge against the exact permitted evidence sent to generation, after reranking and size-based truncation. Adding unused documents or discarded chunks would judge a different context.

Show the answer, context IDs, and explanation for human review. An irrelevant or incomplete answer can still be supported by its context. Groundedness also does not establish that the source itself is true.

### Keep missing evidence and judge failures distinct from negative verdicts

| Situation | Required treatment |
| --- | --- |
| **Explicit pipeline abstention** | Groundedness is `not_applicable`. The abstention remains visible in outcome counts. |
| **An answer appears to contain no factual claims** | Do not automatically infer a special claim-free category or give it a perfect score. |
| **Answered case with no usable bound evidence** | Record a visible input/missing-evidence failure. |
| **Valid boolean verdict that the answer is unsupported** | Record an unsupported judgment, not an execution failure. |
| **Judge refusal, malformed/truncated output, or missing verdict** | Record a judge failure, not an unsupported-answer judgment. |
| **A string such as `"false"` instead of a boolean** | Reject it. Accept only an actual boolean and a bounded explanation. Do not coerce a string into a passing verdict. |

Answers and excerpts are untrusted input. Give the judge no tools, arbitrary endpoints, or release authority. A valid response structure does not prove a correct verdict or resistance to prompt injection. Include hostile excerpts in calibration.

Evaluation evidence follows normal permissions, outgoing-data restrictions, and retention. Keep it in protected evaluation records, not ordinary application logs.

<a id="gateway"></a>

## 3. Keep judging inside the model boundary

ModelGateway handles model calls. The OpenEvals adapter translates the library's requests into that interface without giving the library independent connection or credential settings.

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

This small in-process wrapper is a **facade** over ModelGateway, not an OpenAI client or another router. Any exposed synchronous path must follow the same rule. Return only the response shape OpenEvals reads, then translate results into Inframeld-owned data values (DTOs). Domain code imports neither OpenEvals nor LangChain types.

### Validate the actual direct-client response

The recorded inspection of `openevals/llm.py` found one direct call to `chat.completions.create`, passing messages, model, and strict JSON-schema response settings. It reads JSON from `choices[0].message.content`. This is evidence about the inspected release.

The default output requires a boolean `score`. With `use_reasoning=True`, it also requires a string `reasoning` explaining the verdict. This flag requests an explanation. It does not set the provider's reasoning-effort level.

That inspected path has no retry or schema-repair loop. `json.loads` only parses JSON. Inframeld must still check the exact fields, a real boolean, explanation length, and successful completion.

The recorded source is the [exact OpenEvals 0.2.0 wheel](https://files.pythonhosted.org/packages/4a/8b/00f402b7f3475e235c339a9bc82d2eaf46cc08b53ecd85d4a117850170d3/openevals-0.2.0-py3-none-any.whl), including `llm.py`, `types.py`, `utils.py`, and `prompts/rag/groundedness.py`.

### Bind the library to the admitted run

Bind the facade to the run's authorized connection, model alias, and fixed settings. Check that the library requests the bound model. ModelGateway supplies the allowed output-token limit, reasoning setting, deadline, budget, and IDs linking the call to its operation.

Give the library no independent endpoint credentials. Never pass `judge=None`, which would let it initialize its own model. ModelGateway's adapter handles provider-specific schema translation.

Test the structured-output subset through the actual private gateway. A model supporting it does not prove that a gateway forwards it correctly. The recorded reference covers [structured outputs and refusals](https://developers.openai.com/api/docs/guides/structured-outputs).

### Disable tracing and export explicitly

OpenEvals wraps scoring in LangSmith tracing and logs feedback within a LangSmith test context. Turn tracing off when the worker starts and run the adapter inside `tracing_context(enabled=False)`.

Do not supply LangSmith credentials or exporters, or run this adapter under LangSmith test or experiment tracking. Missing keys or a “standalone” label alone do not prove no telemetry is sent.

The inspected direct path hard-codes an OpenAI provider label in trace metadata. Use ModelGateway's actual provider and model records instead. Verify real network behavior with the locked SDK version. The recorded reference is [LangSmith tracing controls](https://docs.langchain.com/langsmith/trace-without-env-vars).

### Enforce one authorization, budget, and retry policy for evaluation

Every model call uses the authorized ModelGateway path, including pipeline generation, judging, and any future claim extraction, scoring embeddings, repairs, or nested judges. Listing these possible later calls does not add them to v1.

| Boundary | Required behavior and qualification |
| --- | --- |
| **Model-call routing** | Exercise every exposed synchronous/asynchronous path through a recording gateway. No framework receives provider keys. Integration tests block other network destinations, including telemetry and export endpoints. |
| **Whole-run resource limits** | Bound cases, concurrency, deadlines, tokens, and model calls across the complete run. Any later permitted repair consumes the same budget and is recorded. |
| **Retries** | The gateway owns retry policy. Framework/SDK retries must not multiply it. Ambiguous provider outcomes follow [Background jobs, retries, and competing changes](jobs-and-idempotency.md), not a silent replay of the evaluation. |
| **Authorization and configuration** | Fail closed when authorization, connection, alias, required capability, or a valid response is missing. Fail closed means deny or fail the operation rather than continue with a weaker substitute. |
| **Provider and context behavior** | A provider refusal/error is an execution failure, not a quality verdict. No hidden model/provider fallback or silent judge-context truncation is allowed. |
| **Evidence and logging** | Preserve provenance and authorized evidence without credentials. Keep prompts, excerpts, and full answers out of ordinary logs. |
| **Measured behavior** | Measure actual calls, elapsed time, and dependency impact before declaring the integration qualified. |

If a provider response is lost, the call may still have run and incurred a charge. Repeating the whole evaluation could repeat that work. Follow the saved-job recovery rules instead.

The integration tests still need to run. The recorded documentation research executed no evaluation framework, gateway adapter, or judge model.

<a id="cost"></a>

## 4. Choose explicit settings and bound cost

The initial evaluation alias resolves to `gpt-6-luna`. It remains configurable through the same application alias system, including approved private or local gateways. OSS use does not require an OpenAI account.

The proposed trial settings are explicit reasoning effort `none`, strict structured output, and limited explanation and output tokens. Changes discovered during testing become a new evaluator revision.

The source's model documentation recorded Chat Completions, structured outputs, and the `none` reasoning option. Do not assume `none` is the default. The inspected page provided an alias without a separate dated snapshot. Save the resolved model identity when available and check for changes behind the alias.

Fifty answered and successfully judged cases on each of two versions need **100 judge calls**, plus both pipeline executions. Token use depends on their evidence and output. Estimate using the configured connection's applicable rates, then report actual gateway usage, including billable reasoning tokens. Unknown cost remains unknown.

Limit total cases, calls, concurrent work, tokens, and elapsed time. Retries and any later authorized repair share that budget. Historical prices establish neither current cost nor quality. Failed qualification cannot silently select another model or an ensemble.

<a id="history"></a>

## 5. Retain evidence and compare fairly

Each run records its ordered case revisions, Pipeline and corpus versions, profiles, ready indexes, retrieval and generation settings, and the effective caller and permission revision. These identify what ran and what evidence it could use.

Keep the exact final context within the declared size bound, or an immutable protected artifact that can reconstruct it. Record ordered chunk and DocumentVersion IDs. A hash alone cannot show a reviewer missing source text.

Also save the answer and citations, outcome, selected search and reranking observations, evaluator revision, verdict and explanation, gateway call IDs, observed model, and usage.

Intermediate search IDs and scores have a declared retention bound. Full vector dumps and unlimited traces are unnecessary.

### Preserve useful evidence without promising complete diagnosis

These records can help explain missing sources, changed ranking, unsupported additions, or judge disagreement. They cannot replay every execution detail or guarantee a root cause for every old result.

Keep evaluator interfaces and versioned history/detail responses owned by the application. A future diagnostic feature could read this evidence and suggest causes or remedies without rewriting history.

That diagnostic interface and implementation are deferred. Do not add an unused port or let evaluation edit Pipeline settings automatically.

### Compare only cases that are meaningfully comparable

A run can complete without enough evidence for a conclusion. Completion describes the work. Comparability describes whether compatible retained results support a fair assessment.

Keep partial results and metric failures visible. Compare paired changes only where both versions were successfully scored under compatible conditions. Show the valid paired count alongside eligible cases and each side's missing or failed results.

**Never claim an improvement by dropping failed candidate cases from view.**

| Comparison type | Required interpretation |
| --- | --- |
| **Same-corpus comparison** | Benchmark/case semantics and evaluator revision match, corpus revisions match, and permitted document scope is equivalent. Declare the pipeline configuration changes being evaluated. |
| **Corpus-change comparison** | Source revisions intentionally differ under the same benchmark and intended labels. Declare that change. Logical-document labels may survive the update. Missing exact-version labels remain visible mismatches. |
| **Incompatible comparison** | Changed questions/expected meaning, metric definitions, or unsupported differences in authorization scope prevent a like-for-like improvement claim. |

Unchanged cases across benchmark revisions may still be compared if scoring definitions and effective access match. Show exclusions and coverage. Unchanged questions do not make different rubrics comparable. Rerun both versions under one evaluator.

Results apply to the permissions used for that run. A broad-access engineer's result does not establish what a bot with fewer readable documents will do.

Check current access before displaying or exporting saved evidence. Recording the permissions used in the past does not grant access today.

<a id="qualification"></a>

## 6. Calibrate before relying on the judge

**Calibration** checks the selected judge against a small set reviewed by humans using the intended rubric. Another model's opinion is not ground truth.

From the proposed 20–50 questions, manually review a limited subset, such as 10–15 answers, against exactly the contexts they received. Label whole-answer support and note specific unsupported or contradicted statements.

Include supported answers, invented additions, changed numbers, negation, mixed support, arithmetic, abstention, long evidence, and prompt-injection attempts. Keep several examples out of tuning. Mark disputed human labels and exclude them visibly until resolved.

### Measure errors as well as agreement

Measure agreement on undisputed cases where the metric applies, false passes, output failures, calls, tokens, time, and cost. A **false pass** is a judge accepting an answer humans labelled unsupported.

The proposed initial criteria remain open for agreement:

| Proposed criterion | Interpretation |
| --- | --- |
| **At least 90% whole-answer agreement** | Report the numerator and denominator on the labelled sample. This is not a production-accuracy estimate. |
| **No false pass on deliberately seeded critical contradictions** | Test the chosen critical examples explicitly. Do not hide a miss inside an aggregate. |
| **All invalid outputs and failures remain visible** | Output failures are not discarded or converted into quality verdicts. |

These small-sample checks are not automatic release gates. Measuring claim-extraction coverage matters only if that separate metric is selected later, not for this whole-answer judge.

### Check repeatability without selecting favorable results

Run **five fixed borderline or adversarial examples three times each**, without changing settings. Keep every result and report changes in verdicts and explanations.

An apparent improvement similar in size to that observed variation is inconclusive. Fixed settings, deterministic arithmetic, and temperature zero do not make model outputs deterministic.

Repeat calibration after changing the library, prompt, model, gateway capabilities, or material language or corpus characteristics. Start with Luna. Trying a different judge after failure is a new explicit decision, not an automatic fallback.

<a id="release"></a>

## 7. Keep evidence separate from authority

Evaluation informs a decision. Neither a score nor a completion webhook changes which version serves requests.

| Publication mode | Who authorizes publication | How comparison behaves |
| --- | --- | --- |
| **Manual releases** | An engineer explicitly requests the release in Inframeld, or an authorized API client invokes the same application operation. | Results inform that decision. They do not make it. |
| **Automatic updates** | The authorized source/configuration action described in [From a new account to a first useful answer](onboarding.md) supplies publication authority independently of evaluation. | Comparisons remain explicit and bind exact versions. Starting one does not pause automatic publication. |

A manual release separately checks permissions, readiness, duplicate-request identity, and the expected Deployment revision. Those checks prevent a retry from publishing twice or overwriting another person's change.

Record the requesting principal and its kind, the evaluation reference, and acknowledgment of missing, failed, inconclusive, or regressed evidence. Limit any optional rationale's size. [Access](access-control.md) governs humans and applications. An external CI service is not required to own this decision.

Automatic updates run no hidden judge and claim no approved benchmark. Switch to Manual releases when the live endpoint must stay fixed during review. Finishing a comparison changes neither mode nor release target.

<a id="maintainer-checks"></a>

## 8. Maintainer checks

| Scenario | Expected outcome |
| --- | --- |
| Alice edits a test after admission | Both runs retain the frozen case revision. |
| P13 fails a case that P12 completed | Show the failure and paired coverage. Do not drop it to claim improvement. |
| The judge returns the string `"false"` | Reject the shape. Do not coerce it into a boolean verdict. |
| Final evidence differs from initial retrieval | Judge only the exact context generation received. |
| A library attempts telemetry or its own provider client | Block the bypass and qualify actual network behavior. |
| Permission is revoked before history is read | Deny the protected content despite the retained historical scope. |
| A comparison finishes in Automatic updates | Record its evidence without pausing or publishing the endpoint. |
| An external model alias changes behind the same name | Matching identifiers do not establish comparable behavior. |

<a id="decision-map"></a>

## 9. Decision and reference map

Library integration, judge calibration, metric edge cases, and proposed thresholds remain work to verify.

Deeper diagnosis, automatic remedies, custom rubrics, correctness or relevance judges, generated datasets, claim extraction, ensembles, and optimization remain deferred. Keep the application-owned evidence and read contracts without unused diagnostic ports or exporters. LangSmith and Langfuse are not Compose dependencies.

Future exports must preserve internal IDs, current access, and retention. They cannot change run or release outcomes or rerun the judge. External references may use their own namespace without replacing internal identities.

| Decision | Rationale |
| --- | --- |
| [ADR-0030](../adr/ADR-0030-use-openevals-for-groundedness-evaluation.md) | Use OpenEvals for groundedness evaluation. |
| [ADR-0031](../adr/ADR-0031-compare-fresh-executions-against-frozen-benchmarks.md) | Compare fresh executions against frozen benchmarks. |
