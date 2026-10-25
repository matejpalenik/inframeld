---
name: inframeld-pipelines
description: Explains and reviews Inframeld working configuration, direct queries, builds, answer execution, receipts and feedback. Use for the RAG development loop, not GitHub CI workflows or release transitions.
---

# Inframeld Pipelines

Help a developer follow a configuration change through a useful answer. Pipelines owns saved working configuration/history, execution-input snapshots, builds, query orchestration, receipts and feedback. Indexing supplies verified preparation. Releases separately chooses which ready version serves traffic.

## Working model

Alice edits working revision 17 and tries a question with a temporary reranker override. The query captures exact effective settings and corpus before preparation. Later edits cannot change that admitted execution. The override does not save the Pipeline or publish traffic.

A PipelineVersion is the successful result of a release build. It differs from working history and a captured execution-input snapshot. Production is a Deployment that selects a ready version, not a mutable working copy. A direct Pipeline query and a query to Production therefore have separate exact-resource permissions and provenance.

Alice can evaluate two fixed configurations before building. Desired changes must be explicitly saved before CLI Build captures current saved settings. An evaluation run ID does not become the build input. A ready version remains separate from permission to publish it.

## Essential rules

- Keep one ordinary execution path for direct queries, evaluation and serving. There is no Experiment resource, second query service or quickstart authority model.
- Capture exact settings, corpus and verified bindings. Prompt/reranker changes may reuse prepared data. Chunking, embedding or corpus changes may need disclosed paid preparation.
- Build publishes verified readiness. An explicit CLI workflow may coordinate a separate conditional publication under the selected mode and current target authority.
- Shared connections have current access settings. Manual mode and Pipeline rollback do not restore old connection configuration or secrets. Relevant access changes stop subsequent dispatch.
- ModelGateway owns all remote model work. Missing required shards, credentials or reranking cannot justify another provider or unfiltered fallback.
- Live AnswerReceipts retain exact version and evidence attribution. Lost-answer replay is receipt-only. Direct-query/evaluation results do not enter production feedback statistics.
- Feedback, tracing and query execution have different authority and retention. A tracing-only failure or opt-out does not cancel a healthy query or weaken required business checks.

## Explain or review

1. Name the current working revision, captured execution input, ready version and serving target involved in the example.
2. Trace query, explicit save, Build and any separately authorized publication. Explain where each owner participates.
3. Include changed inputs, missing dependencies, a lost response or revoked access. Explain what remains saved and what may safely continue.
4. For result claims, identify actual model/configuration and evidence attribution. For implementation claims, inspect code and separate accepted contracts from qualification.
5. Cite the relevant rule. Loading this skill authorizes no edits, paid calls, releases or external mutations.

Before domain-specific backend component design, code generation or structural review, read [this module's architecture](references/architecture.md) and the relevant workflow, together with Coding Standards. Its accepted design, inspected implementation and proposals have different status. Resolve a pending architectural choice before suggesting code that depends on it. Behaviour-only questions can go directly to their workflow.

## Read as needed

- For module responsibilities, collaborators, data ownership or component design/review, read [Architecture](references/architecture.md).

- For working history, direct queries, overrides, portability or Build input selection, read [Configuration, queries and builds](references/configuration-queries-and-builds.md).
- For context assembly, model settings, current checks or answer recovery, read [Answer execution and receipts](references/answer-execution-and-receipts.md).
- For ratings, reports, trace policy or history deletion, read [Feedback and tracing](references/feedback-and-tracing.md).

The [Pipelines and Releases guide](../../../docs/development/pipelines-and-releases.md) owns current behavior. [Pipeline records](../../../docs/development/data-model.md#pipelines), [feedback](../../../docs/development/answer-feedback.md) and [observability](../../../docs/development/observability.md) own their detailed contracts. Use the Releases skill for publication modes, canaries and rollback.
