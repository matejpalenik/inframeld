# Fence stale automatic publication

Alice switches Automatic to Manual and back while B is preparing. B may become ready, but its former publication authority stays invalid. A fresh authorized request must pass current serving and control guards.

<a id="mode-changes-and-races"></a>

## Apply accepted PD-RELEASES-01

Accepted [PD-RELEASES-01](decision-deployment-state-and-concurrency.md#approved-resolution) selects this workflow's detailed contract. An automatic update is building while Alice switches Production to Manual and back to Automatic. Bob might promote, roll back or change the default route at the same time. Checking only the current mode could revive an old update's authority and overwrite a newer decision. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## Mode changes and races

The default onboarding path starts Automatic updates. Explicit new Deployments default Manual releases with an explicit automatic option. Mode belongs to each Deployment, not every Deployment of a Pipeline.

Automatic to Manual advances control revision and invalidates pending publication while allowing useful preparation to finish.

Manual to Automatic freezes selected inputs and admits fresh work. Even a 0% attached candidate blocks the switch. Re-enabling starts by reviewing the currently serving version's configuration, with any different saved selection explicit.

Off/on cannot revive an old job. The new admission has new publication authority rather than restoring the authority invalidated by the earlier switch.

Shared connection administration can change live connectivity even in Manual mode. It has separate current authority and backend review. Pipeline rollback does not restore connection access settings or credentials. Reject incompatible/unproven shared embedding changes before mutation. Use another connection and the ordinary query/build/release path for an isolated migration.

<a id="publish-only-the-newest-request-whose-original-authority-still-holds"></a>

### Publish only the newest request whose original authority still holds

Two small values tell the worker whether its publication request is still valid:

| Guard | What changes it |
| --- | --- |
| **Monotonically increasing control revision** | Mode switches, changes to the automatic-update binding, and explicit invalidation. |
| **Newest authorized update-request identity** | A newly authorized complete live-input batch or policy-controlled automatic Build. Working edits, direct Pipeline queries and evaluation do not supersede publication work. |

Use existing revision mechanisms where they provide these checks. These values do not need a new family of domain objects.

When work is accepted, save both values and the expected serving revision with the job. Finishing a build cannot update those captured values to recover lost permission to publish.

<a id="switch-modes-through-explicit-concurrency-checked-commands"></a>

### Switch modes through explicit, concurrency-checked commands

Switching modes needs permission, an idempotency key, and the expected revision. The key recognizes a repeated request. The revision confirms that Alice is changing the state she actually reviewed.

Reject an outdated decision instead of silently substituting a newer revision. Save the mode change and audit together. Switching itself preserves current, previous, history, and the endpoint. Publication afterward is a separate authorized change.

<a id="automatic-updates--manual-releases"></a>

### Automatic updates → Manual releases

Switching to manual immediately removes pending automatic requests' permission to publish. An in-progress build may finish reusable output, but cannot make it live. Stop work not yet sent where practical using existing cancellation rules. A provider request already sent cannot be promised canceled.

No re-upload or index copy is needed. A successful switch leaves the version then current in place.

Publication and switching can race:

| Which transaction commits first? | Result |
| --- | --- |
| **The switch** | The old automatic publication fails its guard. |
| **The publication** | It changes the Deployment revision. A switch expecting the old revision conflicts and leaves the mode unchanged. The user reloads and makes a fresh decision. |

After a conflict, the client must reload and obtain a fresh decision. It cannot update the revision and retry blindly, or show automation as disabled when the switch failed. Switching modes also does not undo a release already saved.

<a id="manual-releases--automatic-updates"></a>

### Manual releases → Automatic updates

The action is Enable automatic updates and apply pending changes. Show Alice the complete document selection and configuration. Save the mode change and a fresh update for those exact inputs together.

Initially display the current version's configuration, or validated selected settings before first publication. Alice must explicitly choose any different saved settings. Do not revive old automatic settings after a manual release or include unselected drafts.

Applying the selection is part of enabling automation, not a surprise postponed until the next upload. Missing models, documents, or a complete selection block the command and leave the mode unchanged. Explain what is missing. The newly provisioned default can still start automatic before inputs exist because it has not accepted an update yet.

An attached candidate, even at 0%, blocks enabling automation with `409 candidate_active`. Alice must promote or reject it in manual mode first. Enabling automation cannot silently cancel a trial or alter its percentage.

Keep current serving until the new update succeeds. If it fails, automatic mode remains selected and the failure stays visible under normal retry rules. If the selected inputs already match current, report up-to-date without rebuilding just to switch modes.

**Never restore an earlier disabled job’s publication authority.** Enabling automation is a fresh decision even when it can reuse earlier artifacts.

<a id="run-at-most-one-active-automatic-update-per-deployment"></a>

### Run at most one active automatic update per Deployment

When another authorized batch arrives, save its complete selection as the newest request. Mark older waiting requests skipped or canceled rather than run them simply to empty the queue.

An older build already running may finish reusable artifacts. It cannot publish after a newer request replaces it. The worker next handles the newest eligible request.

The new selection includes chosen existing documents as well as new files. Skipping an older update must not silently discard source changes already accepted.

<a id="check-all-publication-conditions-in-one-transaction"></a>

### Check all publication conditions in one transaction

Immediately before making a version live, check all of the following in one database transaction:

| Check | Required condition |
| --- | --- |
| **Publication mode** | Automatic updates is still selected. |
| **Control and request identity** | The captured control revision and newest authorized request identity still match. |
| **Job ownership** | This attempt still owns completion. |
| **Expected serving state** | The current Deployment or default binding still matches the captured expectation. |
| **Candidate** | No candidate is attached. |
| **Permissions and inputs** | Current authorization and input lifecycle still permit the result. |
| **Readiness and retention** | All required dependencies are ready, and relevant deletion/retention gates still allow publication. |

Save the checked reference changes and history together. First default creation and mode switching must lock and check the same binding, so they cannot establish two competing mode settings. First creation also rechecks the initiating human's Create Deployment permission and saves the explicit creator grants together.

If someone else already created the Deployment, a request to create it does not authorize updating it. Keep the normal expected-state and retry rules. A queued job cannot refresh its own permissions or substitute a different creator.

If the newer request is saved first, skip old publication. If old publication finishes first, that version can serve while the next one is prepared. Neither order lets an old job overwrite a newer published version.

Failure of the newest request never revives an older request or publishes its selection as fallback. Continuous changes may delay publication. Show current and pending state clearly rather than add an unlimited scheduler.

<a id="example-switching-off-and-on-does-not-revive-an-old-update"></a>

### Example: switching off and on does not revive an old update

| Event | Control revision and authority |
| --- | --- |
| **U1 is admitted for P13 in Automatic updates.** | U1 captures revision **10**. |
| **The user switches to Manual releases.** | Control advances to **11**. U1 loses publication authority. |
| **The user enables Automatic updates again.** | Control advances to **12**, and a fresh request U2 is admitted. |
| **U1 finishes late.** | It still carries **10** and cannot publish, even though the mode is automatic again. |

U2 can reuse P13's compatible artifacts, but represents a new choice and input snapshot. Checking only whether automatic mode is currently on would wrongly allow U1 to publish.

<a id="retries-preserve-identities-cancellation-does-not-undo-history"></a>

<a id="retries-preserve-identities-and-cancellation-does-not-undo-history"></a>

### Retries preserve identities and cancellation does not undo history

Repeated acceptance keys find the same operation, and repeating completion cannot publish twice. Show exhausted retries, uncertain provider calls, and unavailable dependencies as their distinct outcomes.

Canceling an update removes pending permission to publish, without undoing a saved release or reviving an older request. If the process crashes after publication but before acknowledging the job, recover the recorded publication ID instead of changing the release again.
