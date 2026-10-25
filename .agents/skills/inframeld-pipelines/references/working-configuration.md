# Edit and restore saved Pipeline settings

Alice saves a different reranker. The working revision changes, while admitted questions keep their captured inputs. Restoring old settings creates a new working revision and does not roll back Production.

<a id="working-configuration-direct-queries-and-builds"></a>

Alice wants to try a new reranker before changing Production. She edits the Pipeline's working settings and queries that Pipeline directly. This development loop should be useful before a release build and should not create another execution service or a hidden publication path.

<a id="show-the-state-that-actually-changed"></a>

## Show the state that actually changed

For change review, distinguish Current / Proposed intent, confirmed Before / Now effects and Reviewed / Now state changes since review.

A saved-revision delta does not change an already admitted build. Ready output is not a live-version delta. Keep unchanged build/live facts neutral and retain current-authority/revision guards. Follow [Pipeline change review](../../inframeld-application-contracts/references/cli-change-review.md#change-review) and [shared CLI deltas](../../inframeld-application-contracts/references/cli-change-review.md#cli-change-presentation) for exact presentation.

<a id="working-configuration"></a>

<a id="edit-one-working-configuration-without-changing-traffic"></a>

### Edit one working configuration without changing traffic

V1 Pipeline/Deployment provisioning is human-only. [Fixed creator assignments](../../inframeld-access-models/references/actions-and-initial-grants.md#initial-assignments) initialize thirteen Pipeline and seven Deployment actions. Applications may edit supported existing configuration, build versions and manage releases through separate explicit eligible grants. Producing revisions/versions is ordinary workflow output. It does not permit creating another Pipeline or Deployment. Before a default Deployment exists, first publication still requires the authorized human creation path.

Alice starts with revision 17 using reranker A. Saving reranker B creates revision 18 and makes it the working configuration. Revision 17 stays identifiable within retention. Restoring revision 17 creates a new current revision with those settings. It does not rewrite revision 18 or roll back Production.

Use expected revisions when saving or restoring. If Bob saved another change after Alice reviewed the settings, return a conflict and let her inspect it. Do not overwrite Bob's work or silently retry against a newer revision. Configuration history restores settings and exact references where retained, not erased documents, expired artifacts or revoked permissions. Unsupported old settings may be inspected but cannot execute until their ordinary requirements are satisfied.

Temporary direct-query/evaluation overrides do not save a configuration revision. If Alice likes a tested override, she explicitly saves those settings through the ordinary edit operation before Build. There is no named-experiment or branching subsystem in v1, and no build-from-run shortcut. A run is evidence of an execution, not the authoritative source of the next build.

Saving, restoring, viewing settings or inspecting a configuration diff performs no model call, preparation or publication. This is different from an explicitly admitted evaluation comparison, which executes questions. Saved incomplete settings may support unfinished setup, but direct querying and Build must reject missing required inputs before execution. The protected direct Pipeline query API is separate from the live query API, not a second Deployment or a client-side RAG implementation.

<a id="capture-experimental-inputs-before-preparation-and-preserve-them-on-retry"></a>

<a id="capture-working-configuration-inputs-before-preparation-and-preserve-them-on-retry"></a>

### Capture working-configuration inputs before preparation and preserve them on retry

Alice admits an evaluation of working revision 18, then saves revision 19 while its preparation is running. The existing job retains revision 18, its explicit overrides, exact corpus and eventual fixed verified bindings. Direct-query/evaluation preparation uses ordinary bounded jobs and checkpoints, without creating a release version. No child completion acquires publication authority.

On a repeated request, find the original operation before resolving the current working revision, collection selection or sole Deployment again. The same key cannot capture revision 19 or a newly created target and charge for a second operation. An explicit new request is required for changed inputs. Admission checks expected reviewed revisions. Conflicts are not automatically retried with fresher consent.

The user-facing policy-controlled Build likewise captures the saved configuration and target exactly once. Its ordinary build child records readiness. Only a separately authorized publication child may change traffic. Record ready-but-unpublished distinctly from preparation failure, and preserve a successful build when permission, mode, candidate state or a newer request prevents publication.

Cancellation covers preparation, between evaluation cases and before gateway dispatch. A canceled/superseded workflow cannot later publish merely because a child finishes. Already dispatched model calls may finish and charge. Uncertain outcomes retain `recovery_required`, not an automatic paid retry. CLI Ctrl-C requests cancellation, while `c` only detaches a durable progress view. Reopening a watcher observes the same job without resubmission. Canceling after publication committed cannot undo the release. [Pipelines](direct-queries.md#preview) and CLI development loop own user-visible context and outcomes.
