# Generate starter cases and review exact revisions

Alice has working Support knowledge but no useful regression tests. Generation proposes questions, references and expected passages. Alice reviews them before they become the default benchmark population. Generating a plausible question is not evidence that the Pipeline answers it correctly.

## Follow bounded generation

1. Freeze a permitted corpus sample across documents and sections. Sampling only successful retrieval hits would hide passages retrieval already misses.
2. Reuse processed text with explicit personas, keyphrases and single-hop synthesis. The starter request is 20 single-passage cases. It adds no generation-time embeddings, reparsing or relationship graph.
3. Route extraction, synthesis, judging and repairs through ModelGateway using explicit generator/judge bindings. Reusing an authorized saved connection needs no second key and does not change Pipeline generation settings.
4. Save proposed immutable revisions as unreviewed. Preserve expected source-version/artifact spans and generation scenario attribution.
5. Show shortfalls and partial failures. Do not regenerate without bounds until the requested count is reached or start evaluation implicitly.

Generated questions and reference answers can reveal their sources. They inherit source protection and erasure obligations. Generation is optional after setup. Finish remains the default completion action, and the first useful pipeline requires neither generation nor a judge.

## Review changes meaningfully

Accept, edit, reject, defer and remove have distinct meanings in the owning contract. Acceptance binds an exact revision. Editing creates a new unreviewed revision.

Previously frozen benchmarks retain their original revisions, subject to erasure. Default regression membership uses currently accepted revisions. Exploratory inclusion of unreviewed cases is explicit and labelled.

Manual blank-form authoring remains deferred. Generation, review and evaluation are separate application operations shared by the CLI and future Studio. Neither reviewing cases nor a favorable comparison saves Pipeline settings or starts publication.

## Failures, status and sources

Changed source bytes cannot retarget an expected passage silently. Missing mappings and unavailable execution inputs have different outcomes.

Current access is checked before model egress and later disclosure. Human/JSON progress shows actual counts and saved results without exposing protected case populations.

Ragas starter generation is the accepted choice under ADR-0051, superseding historical ADR-0030. Inspected library interfaces and a planned CLI journey do not establish an executed end-to-end integration or calibrated judge. Keep the historical first-use journey separate from delivered behavior.

- [Generation](../../../../docs/development/evaluation.md#generation), [review](../../../../docs/development/evaluation.md#review), [result presentation](../../../../docs/development/evaluation.md#result-presentation), [passages](../../../../docs/development/evaluation.md#passages), [records](../../../../docs/development/data-model.md#evaluation) and [CLI delivery](../../../../docs/development/cli-delivery-plan.md).
- [ADR-0051](../../../../docs/adr/ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md) explains Ragas scope. [Onboarding](../../../../docs/development/onboarding.md) owns optional first-use completion.
