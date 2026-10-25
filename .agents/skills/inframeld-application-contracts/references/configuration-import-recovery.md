# Continue a partial import without replacing its meaning

Bob’s import completes several child operations before a later revision conflict. Completed effects remain saved. Recovery inspects the original inputs and child outcomes before repeating any uncertain write.

<a id="captured-import-inputs-and-durable-outcomes"></a>

## Captured import inputs and durable outcomes

These records support the existing domains. Their presence does not add services or a generic workflow engine.

<a id="cli-first-supporting-records"></a>

<a id="records-used-across-workflows"></a>

### Records used across workflows

The records below explain coherent export and reviewed import. Neighboring owners retain spending, tracing, source credentials and evaluation datasets. They describe information the application must retain, not new migrations or a separate table for every concept. Exact representations and qualification remain with their focused owners and linked pending decisions.

| Logical information | Owner and constraint |
| --- | --- |
| Coherent export capture and reviewed import | Existing resource owners retain definitions. Ordinary jobs retain captured definition content/revisions, original context, destination IDs, reviewed choices and relevant expected state, per-resource outcomes and child/parent operation identity. Distinguish create/update effects from reuse and confirmed non-application from unknown write outcomes. No imported grant, credential, Deployment, version or vector state. Missing files are not deletion instructions. |

For imports, save the reviewed input so editing a local TOML file cannot change what the original operation means. Keep completed actions attributed to that operation. A newly reviewed import must not rewrite an earlier import's partial history.

Whether unfinished work can resume depends on current access, dependencies, retained evidence and relevant revisions, not just its completed count. Derive counts and permitted details from existing per-resource outcomes rather than a new tracking store. Reuse is an outcome, not a resource change. [Import recovery](#import-recovery) owns the workflow. The portability and job contracts still need exact schemas and links between operations. This guide does not introduce physical tables or job-state names for them.

See [spending](spending-and-accounting.md#spending), [observability](../../inframeld-pipelines/references/query-tracing-and-privacy.md), [portability](configuration-export-and-import.md) and [Evaluation transfer](../../inframeld-evaluation/references/history-and-dataset-transfer.md#dataset-portability) for execution and failure behavior. These records cannot become a permission, tracing-policy or retention bypass.

An immutable version keeps its recorded meaning. It can still become unavailable through expiry, erasure, corruption, or lost storage. Keeping an old version does not preserve old permissions.

<a id="import-recovery"></a>

<a id="an-interrupted-import-keeps-its-original-meaning"></a>

### An interrupted import keeps its original meaning

[The v1 provisioning boundary](../../inframeld-access-models/references/actions-and-initial-grants.md#provisioning) rejects application plans requiring new configurable resources before known-ineligible mutations. Eligible updates to existing resources retain the recovery rules below. Later permission/state changes can still leave confirmed partial effects. They never authorize replay as a human or creating missing dependencies.

Bob's import creates two resources and reuses three existing ones. Before its final step, the Pipeline changes, so the reviewed update can no longer be applied. Preserve the five confirmed outcomes and report the unapplied action. Do not undo the creates or replay completed updates.

Reusing a resource does not write it. Any remaining step that needs it must still check its current state and permissions. The [worked import example](#import-recovery) explains the resource workflow and terminal output.

Recovery first finds the original admission/job under its original context. An unchanged, retained review can support explicit continuation of eligible unfinished work through ordinary current checks. Changed definitions, mappings or relevant state instead require fresh review/admission. They cannot replace the old job's inputs. A new reviewed import may reuse completed resources after current comparison, while the old partial history remains intact. Exact relationship/projection contracts remain work, not a new generic workflow engine.

An uncertain child write is neither a confirmed success nor a confirmed failure. Reconcile its original command/result before repeating it. Replaying an earlier successful response must not restore old configuration over a later edit. Lost local connectivity does not prove failure, and missing authoritative history does not prove absence of effects. Report those limits without silently creating another import. Cancellation prevents only work the ordinary cancellation boundary can stop. It cannot undo committed resources or eliminate the need to reconcile a late write. No import recovery implicitly calls models, syncs documents, builds or publishes.

<a id="durable-import"></a>

## Durable Import

1. Bind the reviewed definitions, mappings, current authority and expected destination revisions to the original operation.
2. Invoke existing domain-owned operations in dependency order. This is orchestration inside the existing backend, not a new domain, generic provisioning engine or global transaction across external work.
3. Persist each resource result. Already completed resources remain after interruption. Omitted resources are never pruned.
4. Recover original admission/job before repetition. Continue eligible unfinished work under current checks. Changed inputs or relevant state need fresh review. Reconcile uncertain writes before retrying.
5. Report configuration, credentials, data, preparation, evaluation and publication as separate outcomes. Finish is the default. Optional continuation reuses ordinary screens and separately authorized operations.

New collections are empty. Imported sources do not synchronize. No documents, model calls, embeddings, builds or release transitions occur merely because import succeeded.

<a id="follow-one-import-through-success-and-interruption"></a>

## Follow One Import Through Success and Interruption

Bob reviews six resource actions for `legal-research`: create two collections, reuse three matching dependencies and update the saved `contracts` Pipeline. The matching dependencies retain their IDs and credentials. The Pipeline update changes working configuration only. The reviewed import and recovery ticket makes three existing rules concrete. It does not introduce another import engine or a transaction spanning the whole project.

<a id="case-1-the-reviewed-actions-still-apply"></a>

### Case 1: the reviewed actions still apply

Invoke ordinary domain operations in dependency order. Create missing resources, reuse matching ones without manufacturing revisions, and apply only explicitly reviewed supported updates. A reused resource must remain suitable and accessible when remaining work needs it. A name is not proof of equivalence, and a previously successful reuse check is not permanent authority.

On confirmed completion, report **Created 2, Reused 3, Updated 1** for this fixture. Configuration is saved, but credentials, documents and indexes may still be missing. Finish remains the default. Import does not synchronize sources, test providers, evaluate, build, create a Deployment or publish. Shared-current connection updates, if separately selected, retain their normal live-impact guards. "no publication" is not "no possible effect on live connectivity."

<a id="case-3-the-destination-changes-after-some-work-completes"></a>

### Case 3: the destination changes after some work completes

In a separate run, two creates and three reuses complete before a changed Pipeline revision blocks its update. The following is **mock, unimplemented presentation**, assuming current access permits the listed facts:

```text
Import incomplete

Created      2 resources
Reused       3 resources
Not applied  1 pipeline

The pipeline changed after your review.
Completed changes were kept.

Next: review the pipeline change before continuing.
```

"Not applied" here means the owner confirmed that the guarded Pipeline update did not commit. If the write outcome is unknown, show that uncertainty instead. Neither success nor failure can be inferred from a timeout. Counts come from protected retained resource outcomes, with a bounded detail view naming the affected resources and reasons where access permits. Do not hide unattempted, failed or uncertain actions inside a success count. Reused resources are resolved outcomes, not writes performed by the import.

Keep confirmed completed effects. There is no automatic rollback, deletion of newly created resources, replay of completed updates or restoration over newer state. A changed review needs a fresh explicit reviewed import, which may deliberately reuse earlier completed resources after current comparison. The original operation retains its partial history. Approval of changed definitions/state must not rewrite its meaning. Exact linkage between old and new work remains specification work, not a new plan-resource API.

<a id="recover-the-original-operation-before-deciding-what-to-do-next"></a>

### Recover the original operation before deciding what to do next

| Observed situation | Next allowed action |
| --- | --- |
| The CLI disconnected and original work may still be running | Look up the original admission/job, then inspect or watch. Do not submit a second import merely because the terminal lost contact. |
| Unfinished work is confirmed eligible under the unchanged reviewed input and current checks | Explicitly resume the same operation, skipping completed mutations. A historical success does not bypass current dependency/access checks. |
| Local TOML changed | The old job still means its retained original definitions. Using the new files requires new review/admission, not implicit file rereading on resume. |
| A required revision, identity, permission or live-impact review changed | Stop stale continuation. Preserve completed work and obtain a fresh valid review. Never silently retarget or adopt newer state. |
| A child write's acknowledgment was lost | Reconcile the original child identity/result before repetition. A later edit must not be overwritten by replay of an earlier success. Unknown remains unknown until authoritative evidence resolves it. |
| Required retained input/history is unavailable | Explain the recovery limit. Do not infer that no effects occurred or reconstruct permission from local names/counts. Any new work needs explicit review. |

Current permissions govern both effects and disclosure, including resource names, counts and stored definitions. Dry-run describes the plan and unavailable checks without mutation/admission or becoming later approval. Scripts provide required choices, return structured conflicts/partial outcomes without prompts, and never switch to a saved human identity. Human progress uses stderr when stdout carries JSON. Ctrl-C requests cancellation without undoing committed resources. `c` detaches the watcher only. [Jobs](#import-recovery) owns these shared retry/cancellation boundaries. The import contract must define exact reviewed inputs, equivalence and revisions before implementing destination review and guarded durable application. Qualification must verify stale-before-mutation, post-partial races, missing credentials, lost acknowledgments, changed files, duplicate resume, current access and zero hidden execution. Retain shared recovery/output contracts. These are accepted requirements and future qualification scenarios, not implemented APIs or test results.

## Qualification still required

Before declaring portability supported, settle exact schemas/defaults, semantic equivalence, source-coordinate proof, capability/target mapping, revision review and recovery output through the relevant pending contracts. Qualification must cover complete round trips, local overwrite races, concurrent destination edits, expired authority, uncertain writes, interrupted imports, retained local edits, hidden sources, erasure and every supported resource. Exported copies already downloaded cannot be recalled across installations.
