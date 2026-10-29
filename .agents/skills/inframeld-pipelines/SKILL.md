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

For backend component design, code generation or structural review, read [module architecture](references/architecture.md), the affected workflow and Coding Standards. Behavior-only questions go directly to their workflow. Pending proposals do not authorize dependent code.

## Accepted contracts for affected work

Load the accepted contract matching the trigger. The developer resolved these policies on 2026-10-29. Do not request the same decisions again. Native representations and qualification remain implementation work. A later policy change follows [decision finalization](../../../docs/development/guides/architecture-decisions.md).

- [PD-PIPELINES-01](references/decision-execution-build-receipt-contracts.md): Before defining captured input/build/execution interfaces, preparation continuation or receipt admission/finalization.
- [PD-PIPELINES-02](references/decision-trace-policy-fencing.md): Before implementing trace capture/buffering/export delivery, opt-out acknowledgment or history-deletion fencing.

For a narrow feedback or tracing question, open its focused reference directly. Receipt attribution after promotion does not require Releases, and feedback counts do not require Evaluation unless the question asks about their release or metric behavior.

## Read as needed

Choose the row matching the task. Workflow, contract and architecture views are separate reading units. Do not load this whole table.

| Task | Direct reference |
| --- | --- |
| Answer execution and receipts | [Execute an answer and preserve its attribution](references/answer-execution-and-receipts.md) |
| Answer feedback | [Submit and correct feedback on an answer](references/answer-feedback.md) |
| Module/component design or structural review | [Pipelines architecture: execute the inputs the caller selected](references/architecture.md) |
| Build preparation | [Build a ready version without granting publication](references/build-preparation.md) |
| Editing/query/build distinctions | [Working configuration, direct queries and builds](references/configuration-queries-and-builds.md) |
| Direct queries | [Try a question against captured working inputs](references/direct-queries.md) |
| Feedback versus diagnostic tracing | [Feedback, query traces and history](references/feedback-and-tracing.md) |
| Feedback reporting | [Read feedback reports with honest coverage](references/feedback-reporting.md) |
| Query tracing and privacy | [Query tracing, privacy and diagnostic failure](references/query-tracing-and-privacy.md) |
| Logical records and representation ownership | [Pipeline configuration, execution inputs and receipts](references/records.md) |
| Reranking and context assembly | [Rerank evidence and fit the final context](references/reranking-and-context-assembly.md) |
| Trace capture and deletion | [Stop trace capture and delete selected history](references/trace-capture-and-deletion.md) |
| Working configuration | [Edit and restore saved Pipeline settings](references/working-configuration.md) |

## Source ownership

Focused references own accepted behavior and logical design. Code, generated OpenAPI and migrations own implemented representations. Read exact definitions when fields matter, ADRs for rationale or conflicts, and matching pending decisions before dependent design. Human guides own development procedures.
