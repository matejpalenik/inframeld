# PD-RELEASES-01: Persist Deployment transitions with one shared control check

**Status:** ACCEPTED on 2026-10-29 in [ADR-0110](../../../../docs/adr/ADR-0110-serialize-release-control-with-expected-revisions.md). Implementation and qualification remain separate delivery work.

**Owner:** `inframeld-releases`

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Contents

- [Approved resolution](#approved-resolution)
- [Why and example](#why-and-example)
- [Implementation and required evidence](#implementation-and-required-evidence)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Historical context and alternatives](#historical-context-and-alternatives)
- [Sources and finalization](#sources-and-finalization)

<a id="non-binding-recommendation"></a>

## Approved resolution

Use one complete bounded Deployment control snapshot and one common SQL coordination/save contract for all competing transitions. Serialize control writes through the relevant Deployment record in a short transaction, while retaining the caller's expected revision as a stale-decision check. A lock protects the write ordering. It does not authorize silently retrying a stale human decision against newer state.

The trusted snapshot includes scope and lifecycle, current/candidate/previous version references, rollout identity and percentage, publication mode, selected automatic input/configuration binding, Deployment revision, publication-control revision and newest authorized update-request identity. Transition services separately obtain exact ready-version/dependency facts, current actor permissions, attempt ownership and applicable expected default-binding state. Keep documents, model calls and unbounded job/history collections outside the aggregate. Repositories do not commit or retry.

Every automatic update admission/publication, mode/input-binding change, candidate attach/adjust/reject/promote, rollback, deletion and affected default-route change must use the same relevant gates and final conditional revision/lifecycle save. Coordinate with current Access and dependency-retention gates in one documented consistent lock order. Take Project/default-binding coordination before Deployment coordination whenever both are needed; sort multiple identities consistently. Do not call independently transaction-owning complete services inside the transition. No provider, Chroma or artifact wait occurs while SQL locks are held.

Publication rechecks current authority/input lifecycle, exact same-Project compatible ready version and dependencies, original attempt fence, expected serving/default state, publication mode/control revision, newest authorized request and absence of a candidate together. Commit pointers, retained references, relevant revisions, history, required audit, operation completion and safe replay outcome together. A committed release recovered after lost acknowledgment returns its original publication identity instead of applying the transition again.

New complete authorized live-input work or policy-controlled automatic Build advances newest-request identity. Mode/input-binding changes invalidate old publication through the control revision. Every actual Deployment state change advances its state revision. Captured requests cannot refresh those guards themselves. Working saves/restores, direct questions and Evaluation do not supersede publication work.

Switching Automatic to Manual removes old pending publication authority while preserving serving pointers/history. Switching back advances control and admits a fresh reviewed exact update, or a confirmed up-to-date outcome without unnecessary model work. Never revive the earlier request. An attached candidate, including 0%, blocks enabling Automatic. Manual-only canary/promotion/rollback rules remain unchanged. Reject a candidate without changing current/previous. Promotion makes the old current the designated previous. Rollback requires no attached candidate, uses the eligible designated previous once and consumes that target. Missing/unhealthy/erased targets cannot be replaced silently.

First default creation coordinates through the existing Project/default setup binding because the Deployment does not yet exist. Validate the reviewed binding/control/request state and current initiating-human creation/Build/input authority. In one transaction create the genuinely ready initial Deployment, its current version, ordinary explicit creator grants and default binding, transfer setup control state and record completion/audit. The uniqueness/expected-state guard permits only one first creation. A losing create request cannot become permission to update the winner. Deliberate removal markers survive so an old job cannot resurrect deleted defaults. Explicit nondefault creation retains its ordinary ready-initial-version and chosen mode rules.

When automatic requests overlap, preserve their frozen inputs and individual outcomes. The newest eligible request supersedes older publication authority even when an older build finishes reusable data. A failed newest request never revives an older request as fallback. Each Deployment remains separately controlled; sharing a Pipeline or collection does not create an all-Deployment transaction or shared release permission.

A rejected/stale transition leaves current state intact. If publication commits first, a mode change expecting the old state conflicts and must be reviewed again. If the mode change commits first, old publication is rejected. Database rollback/retry handling cannot repeat remote effects or update the caller's expected revision silently. Safe errors and public shapes follow existing contracts. This selects logical state and coordination, not a final migration/schema catalogue.

## Why and example

An automatic update is building while Alice switches Production to Manual and back to Automatic. Bob might promote, roll back or change the default route at the same time. Checking only the current mode could revive an old update's authority and overwrite a newer decision.

Update U1 captures control 10. Alice switches to Manual, advancing control to 11. She later enables Automatic with a fresh U2, advancing to 12. U1 finishes with its original 10 and cannot publish. If Bob changes serving state before Alice's reviewed command commits, her expected revision conflicts. She sees what changed before making a new decision.

Because all competing actions use the same gate and revision checks, none can slip around another's control decision. The cost is brief contention on the same Deployment. Pure conditional writes could also work, but every path would need equivalent complete predicates. Short serialization plus expected revisions is easier to audit for this single-server product. Locks are released before slow external work.

<a id="decision-trigger-and-stopping-boundary"></a>

## Apply the accepted contract

Use this contract when the original trigger matches. Do not ask for the same policy decision again. Concrete native methods, DTO names and physical schemas are implementation choices consistent with this contract and the repository conventions. Missing measurements, fixtures or assembled evidence block the affected qualification/support claim, not authorized implementation or isolated tests. A failed test is not permission to weaken an accepted safety boundary.

<a id="open-questions-and-required-evidence"></a>

## Implementation and required evidence

Publication versus mode change in both commit orders, off/on without revived authority, competing promotions, rollback with candidate/missing/erased previous, concurrent first creation, default rebinding/deletion, newest-request failure, source/grant loss before commit, stale attempt completion and lost publication acknowledgment. Confirm state/history/audit/outcome atomicity and consistent ordering with authorization/retention.

These are required checks, not tests run or successful production evidence. No application edits, paid calls or production changes follow merely from recording this decision.

## Architectural impact and dependencies

Releases state/repository/services, shared operation completion/audit, Pipeline ready results and onboarding binding. Update mode/publication/manual-transition sequence diagrams and logical record notes.

Load neighboring decisions only under these conditions:

- [PD-KNOWLEDGE-01 (accepted): Finalize a complete collection selection without losing admitted input](../../inframeld-knowledge/references/decision-complete-batch-handoff.md). For complete live-input selection/handoff.
- [PD-ACCESS-06 (accepted): Authorize setup details before a Deployment exists](../../inframeld-access-models/references/decision-setup-read-authority.md). For protected precreation status.
- [PD-PIPELINES-01 (accepted): Capture fixed inputs and complete execution through its receipt](../../inframeld-pipelines/references/decision-execution-build-receipt-contracts.md). For captured ready-build results.

## Historical context and alternatives

The following preserves the earlier problem, context and options. Statements that a choice was open describe that earlier analysis. The approved resolution above now settles it.

<a id="problem-and-example"></a>

### Original problem and example

Historical analysis before this resolution.

Production serves A while B is building automatically. Alice switches Automatic to Manual and back to Automatic. An old attempt then completes. Its data may be reusable, but it must not publish through revived old authority. Bob can also promote or roll back concurrently.

The focused Deployment aggregate and valid transition rules are accepted. Exact loaded state, repository save contract and coordination among publication, mode changes and operator commands remain open. A partial aggregate or inconsistent write check could permit stale traffic changes.

### Original accepted context and evidence

Historical context before this resolution. Unchanged invariants still apply.

Preserve serving/current/previous/candidate meanings, expected revisions, control revision, newest authorized request and attempt ownership. Publication also requires current permissions and healthy complete dependencies. Canary and rollback remain Manual-only, and a candidate even at zero percent blocks Automatic mode.

An aggregate owns cohesive transition rules, while application services obtain current external facts and own transactions. Repositories do not commit or retry. Creation constructs valid first-ready state and binding, rather than loading a nonexistent Deployment. No new physical schema was selected by ADR-0079.

### Considered alternatives and trade-offs

Historical options, resolved by the approved contract above.

1. **Load focused state and conditionally save the expected control revision.** Use a complete bounded snapshot of related serving/mode/control fields and reject mismatched versions at save. This minimizes lock lifetime but requires every competing transition to use the same predicates.
2. **Serialize the focused transition state within a short transaction.** Load the needed state under documented coordination and perform the transition/save together. This simplifies some interleavings but adds contention and requires consistent ordering with authority/dependency checks.

## Sources and finalization

- [Deployment transition boundary](architecture.md#deployment-transition-boundary).
- [Focused aggregate decision](../../../../docs/adr/ADR-0079-protect-deployment-transitions-with-a-focused-aggregate.md).
- [Releases records](records-and-transitions.md#releases).

Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later change to this accepted policy. Qualification evidence must identify its artifacts, environment, failures and limits. This record does not fabricate implementation or a passing test.
