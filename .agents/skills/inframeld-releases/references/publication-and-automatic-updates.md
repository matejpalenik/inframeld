# Publish ready versions under current authority

<a id="publish-ready-versions-under-current-authority"></a>

Alice starts an automatic handbook update, then switches Production to Manual. Preparation can still be useful, but that old request must not move traffic. Releases keeps preparation, publication authority and competing operator choices separate.

<a id="follow-automatic-publication"></a>

## Choose a focused reading task

- For initial ready Deployment and defaults, read [Deployment creation and defaults](deployment-creation-and-defaults.md).
- For mode switches and publication races, read [Automatic publication concurrency](automatic-publication-concurrency.md).

## Follow automatic publication

1. Admit a complete authorized live-input batch or explicit policy-controlled CLI Build. Require the underlying input/mutation rights, Pipeline Build and target Manage releases. Before default creation, onboarding instead needs project Create Deployment.
2. Capture exact selected configuration/corpus and publication-control state. Document-triggered updates use Deployment-selected configuration rather than the evolving Pipeline working copy.
3. Run normal readiness-only preparation. Edits, restores, direct queries and evaluation do not publish or supersede pending publication. Partial inputs and upload-only rights are insufficient.
4. Before dispatch and publication, recheck current authority. Publication checks newest authorized request identity, control revision, selected inputs, current attempt and serving state together.
5. Conditionally change traffic. A stale or failed request leaves healthy current in place. Superseded work cannot become fallback after a newer request fails.

The explicit CLI coordinator selects a sole live Deployment or asks for a choice among several. Never fan out. With none, ordinary Build stays unpublished while the existing first-publication path retains its distinct authority. A competing creation cannot authorize an update to somebody else's existing Deployment.

<a id="choose-how-updates-become-live"></a>

<a id="modes"></a>

<a id="4-choose-how-updates-become-live"></a>

## Choose how updates become live

Both publication modes use the same document versions, builds, ready versions, and query path. They differ in who requests publication and when.

| Mode | Document changes | Pipeline configuration | Release control |
| --- | --- | --- | --- |
| **Automatic updates** | A completed, authorized live-input batch requests a build and publication of its complete frozen selection. | Explicit user-facing **Build** captures saved configuration and authorizes its update for the selected Deployment. Working edits, direct Pipeline queries and evaluation are ignored by publication. | Publish only the eligible, complete, ready result. Do not automatically run an evaluation or start a canary. |
| **Manual releases** | Admit new versions as unpublished inputs. | Edit, query and evaluate without changing traffic. Build creates a ready version. | Use explicit candidate/canary, promote/reject, and rollback actions. Comparison remains available before or after Build. |

A **batch** is a fixed selection of files with explicit limits. **Frozen inputs** save the exact versions and settings chosen for the work, so later edits cannot alter it. A canary tries the candidate with part of the traffic before promotion.

The default onboarding path starts in **Automatic updates**. An explicitly created Deployment defaults to **Manual releases**, unless its creator chooses Automatic updates. Both modes are available at creation and can be changed later.

Publication mode belongs to each Deployment. Test and Production can use the same Pipeline with different modes and selected settings. A client may present the choice during setup, but changing one endpoint does not change all endpoints using that Pipeline. Neither is the protected direct Pipeline query API, which has no publication policy or serving pointer.

<a id="follow-selected-documents-not-every-draft-edit"></a>

### Follow selected documents, not every draft edit

An automatic-update binding records which Pipeline, saved configuration revision, and document collections the Deployment follows. They belong to the same project. Each build saves exact CollectionRevisions and profiles from this selection.

Production can therefore follow authorized document changes without following every working edit to Pipeline settings. The automatic binding is separate from the working-configuration pointer. An explicit authorized Build/update selection changes that binding through the existing control-revision rules. A save or restore does not. Once selected, document-driven work uses that recorded configuration even while Alice experiments with another one.

Direct-query corpus selection fixes exact collection revisions without changing the live binding. To upload development-only documents, use an ordinary collection outside the live-watched selection, with normal source/group permissions. Do not silently create another collection, copy the corpus, or suppress automatic updates on a watched collection. Updating a live-watched collection is a live-input operation and must disclose its publication consequences. Direct querying itself never writes source membership.

The starter flow shows its default automatic mode without another release question. Its upload action explains that a complete change becomes available after preparation. Customers keep the same URL, but later answers can use a newly published version. API, CLI and future Studio show the mode, live version, working revision and pending update separately.

<a id="build-a-ready-version-then-request-publication-separately"></a>

### Build a ready version, then request publication separately

Save one small update operation containing who requested it, its target, captured control revision, request ID, fixed inputs, and stable IDs for its child operations. A child operation is a step such as the build.

```text
Authorized completed live-input batch or explicit policy-controlled Build
    -> Durable update with frozen inputs and publication authority
        -> Ordinary source-admission and Build use cases
            -> Complete ready PipelineVersion
        -> Separate Releases publication command
            -> Publish only if the original request remains eligible
```

Show upload, preparation, ready version, and publication as separate progress stages. If publication is skipped, the new version may be ready while the endpoint still serves the old one.

Releases handles publication. It checks the project and target, readiness, input compatibility, current permissions, absence of a candidate, and whether another change has made this request outdated.

| Publication case | Effect |
| --- | --- |
| **First default publication** | Create the actual Deployment and bind the route in the same short SQL transaction, transferring publication-control state. It has one ready current version and no previous target. |
| **Later eligible automatic publication** | Replace current and retain the former current as the designated one-step previous target. Do not manufacture a canary candidate or traffic ramp. |
| **Result identical to current** | Do nothing to the serving pointers, including the previous target. |

History records the initiating action, mode and control revision, exact versions, and publication outcome. An automatic update must honestly record that it did not include benchmark review. Never invent a passed evaluation or manual approval. Scores and feedback do not initiate publication.

Queries and receipts retain the actual version, Deployment revision, and cohort they selected even after another publication.

Building reports readiness only. The update operation requests publication separately. Indexing and job-completion handlers cannot switch traffic themselves. Saved progress and request identity recover interrupted work without repeating paid calls. Chroma writes may repeat their exact saved payload under the Indexing rules, while an uncertain paid-model call needs explicit recovery. Automatic mode changes neither rule.

<a id="manual-review-canaries-and-rollback"></a>

### Manual review, canaries, and rollback

Attaching candidates, changing canary traffic, promoting or rejecting a candidate, and rollback require Manual releases. In automatic mode, return a clear mode conflict instead of switching implicitly.

Comparisons and history work in either mode. Comparing versions neither pauses automatic publication nor promotes the winner. Choose manual mode first if review needs a fixed serving baseline.

Automatic publication keeps the old current version as previous. Alice can switch to manual and roll back one step if that version remains usable. Rollback uses up the previous reference and leaves the mode manual.

Enabling automation again applies the selected inputs afresh and may replace the version just restored. Explain this consequence. Neither rollback nor restart enables automation automatically.

<a id="reuse-these-rules-for-automatic-publication"></a>

<a id="automatic"></a>

<a id="7-reuse-these-rules-for-automatic-publication"></a>

## Reuse these rules for automatic publication

Automatic updates use these same jobs and keep stable IDs for their child operations. The underlying preparation and publication are separate application commands, even when the CLI Build workflow admits both together. Only one update runs per Deployment at a time. A newer authorized live-input update or automatic Build removes an older one's permission to publish, without changing the older build's fixed inputs. A working edit, restore, direct Pipeline queries or evaluation does not supersede publication work.

The [publication-mode guide](#modes) defines the full checks. A worker cannot substitute a newer revision to make an outdated request valid. After a crash, it finds the recorded release change instead of publishing twice. Canceling pending work does not reverse a release already saved.

<a id="apply-a-complete-authorized-selection"></a>

<a id="updates"></a>

<a id="5-apply-a-complete-authorized-selection"></a>

## Apply a complete authorized selection

Automatic mode starts a workflow, but grants no permissions. For an existing Deployment, enabling it requires Build on the selected Pipeline, Manage releases on that Deployment, and access to the inputs. Applying a source or configuration change also requires permission for that change. Before the first default Deployment exists, the initiating human instead needs Create Deployment, with the same Build, change, and input checks.

Manage releases covers publication, rollback, canaries, mode switches, and automatic-input selection on one Deployment. Edit configuration covers only non-serving details. The [Access rules](../../inframeld-access-models/references/memberships-groups-and-handover.md#section-bound-administration-grants-and-recovery) define that separation.

Save who requested the update and the authority under which it was accepted. Check current project or resource scope and permissions again before sending work and before publishing. A job cannot publish using permission its requester has since lost.

The starter creator receives explicit permissions for the starter project and resources, including Build on the selected Pipeline. Before the first Deployment exists, publication also requires Create Deployment. Creating it assigns Manage releases on that new Deployment. Later updates require current Manage releases on that exact Deployment. The installation-level Create projects permission is separate. Starter setup neither needs nor grants it. Someone with upload-only permission may save source changes, but the CLI must explain that publishing them needs an authorized person. Future Studio follows the same rule. Upload or Query never includes release permission.

When several automatic Deployments use one collection, the operation names each target it may update. Each has its own request and outcome. There is no all-Deployment transaction or use of another person's release permissions.

<a id="take-an-imported-pipeline-live-explicitly"></a>

### Take an imported Pipeline live explicitly

Bob imports his colleague's configuration into an existing project. The import creates supported resource definitions, not documents, vectors, a release version or a Deployment. If he needs a new project, he creates it through the ordinary operation above before returning to a fresh import review.

1. Supply credentials and documents through their existing authorized workflows. Import does not perform these steps or send model requests implicitly.
2. Explicitly Build the saved Pipeline configuration and selected corpus. Review preparation, outgoing data and cost. With no Deployment, successful Build returns a ready **unpublished** version.
3. Use CLI Deployment management to create a Deployment from that exact ready, compatible version. Backend creation checks current Create Deployment authority and readiness. Explicit creation defaults to **Manual**. **Automatic** and its input binding require an explicit choice.
4. Show the endpoint and initial serving version only after creation is confirmed. A lost response requires original-operation recovery, not a second creation or a substituted version.
5. Offer Finish. Creation alone does not change the project-default binding, issue an application key or send a paid test query. Those are separate choices with their own checks.

This journey must be available in CLI v1 without Studio or handwritten API requests. The exact commands and human/JSON/noninteractive/dry-run contracts belong to CLI contract work. The sequence here does not invent final flags or claim the CLI is implemented. The initial starter's separately authorized Automatic create-and-bind flow remains unchanged.

<a id="automatic-updates-still-need-permission"></a>

### Automatic updates still need permission

The default serving route starts in Automatic updates. Other Deployments start in Manual releases unless automatic mode is explicitly selected at creation.

For an existing Deployment, an automatic live-input source update requires permission to make that source change, Build on the selected Pipeline, and Manage releases on **every explicitly selected target Deployment**. A policy-controlled CLI Build captures already saved configuration and requires Build, current input access and Manage releases on its one selected Automatic Deployment. It does not edit the working configuration.

A save/restore separately requires Edit configuration. Sharing a collection or Pipeline does not share release authority. The CLI resolves a sole Deployment or requires a choice, never implicitly publishes to all of them or infers the target from the first visible row.

Changing publication mode requires Manage releases. Enabling automatic updates and applying their selected inputs also requires Build and valid inputs. Switching to manual cancels pending publication authority. Switching back does not revive it. Workers must still check the initiating caller's current permissions. The [pipelines and releases guide](#modes) explains the full lifecycle.

<a id="pending-decisions-for-dependent-implementation"></a>

## Pending decisions for dependent implementation

Before choosing an unresolved implementation contract, load only the entry whose trigger applies:

- [PD-RELEASES-01: Persist Deployment transitions with one shared control check](decision-deployment-state-and-concurrency.md). Before defining Deployment aggregate/repository state or implementing publication, mode changes, promotion, rollback or first binding.
- [PD-KNOWLEDGE-01: Finalize a complete collection selection without losing admitted input](../../inframeld-knowledge/references/decision-complete-batch-handoff.md). Before implementing batch completion, collection selection, parent/child recovery or the ingestion-to-automatic-update handoff.
- [PD-ACCESS-06: Authorize setup details before a Deployment exists](../../inframeld-access-models/references/decision-setup-read-authority.md). Before defining defaults/setup read contracts or implementing HTTP/MCP/CLI prepublication status resolution.

<a id="status-and-sources"></a>

## Status and sources

Publication modes and concurrency guards are accepted design. Scores, feedback, synthetic tests and healthy historical labels are not release authority. Current erasure or unusable dependencies can invalidate targets. Exact action/wire mapping and runtime qualification remain with the owning references and pending contracts.

- [Publication modes](#modes), [Pipelines and Releases](../../inframeld-pipelines/references/configuration-queries-and-builds.md), [Release records](records-and-transitions.md#releases), [onboarding](../../inframeld-architecture/references/first-use-and-private-defaults.md), [Access](../../inframeld-access-models/references/authorization.md) and [creator assignments](../../inframeld-access-models/references/actions-and-initial-grants.md#initial-assignments).
- [Jobs and idempotency](../../inframeld-application-contracts/references/jobs-and-recovery.md), [shared connections](../../inframeld-application-contracts/references/model-connection-changes.md#shared-current), [ADR-0033](../../../../docs/adr/ADR-0033-separate-build-readiness-from-release-authority.md), [ADR-0040](../../../../docs/adr/ADR-0040-bind-pipeline-versions-to-verified-profile-specific-materializations.md), [ADR-0047](../../../../docs/adr/ADR-0047-support-reversible-publication-modes-per-deployment.md) and [ADR-0054](../../../../docs/adr/ADR-0054-use-shared-current-model-connections.md).
