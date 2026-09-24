# ADR-0009: Sticky canaries, candidate rejection, and promotion rollback

**Status:** Accepted — release transitions, affinity, ready initial deployments, and reversible publication modes. **Revised:** 19 September 2026. **Required approach:** Stable Deployment endpoints, deterministic canary routing, and authorized publication through reversible Automatic updates or Manual releases. **Related:** [Evaluation](ADR-0008-deterministic-evaluation-and-release-decisions.md), [idempotency](ADR-0007-durable-jobs-idempotency-and-recovery.md), [materializations](ADR-0015-profile-specific-index-materializations-and-pipeline-bindings.md).

## Context

Inframeld lets an engineer change how a customer AI application answers questions without requiring that application to integrate with a new endpoint for every version.

A **PipelineVersion** contains an immutable configuration for retrieval-augmented generation (**RAG**): retrieving document excerpts and using them to generate an answer. A **Deployment** is the stable endpoint that selects which compatible pipeline version serves a request. Releasing a pipeline changes that selection; it does not upgrade application code or Docker containers.

Before replacing a working version, an engineer may want to try a candidate with a limited group of users or sessions. This is a **canary**. A **sticky canary** keeps each routing identity assigned consistently within the same rollout instead of randomly selecting a version for every request.

From first principles, **trying a version, rejecting that trial, and undoing a completed promotion are different actions**. Rejecting a candidate must not undo the working release it was tested against. Likewise, a slow build must not publish after the user has withdrawn or replaced its publication authority.

This decision defines those transitions, the routing rules, and how manual review coexists with automatic publication. It also explains what happens to requests, evidence, and retained versions when serving changes.

## Decision

**A Deployment changes serving behavior by moving references to complete, immutable pipeline versions. Canary routing is deterministic, every transition is authorized and concurrency-checked, and historical answers retain their original attribution.**

Each Deployment independently uses **Manual releases** or **Automatic updates**. Building a version and publishing it remain separate operations in both modes. Evaluation scores and answer feedback never authorize a release by themselves.

As accepted during issue #24's access analysis, **Manage releases** is the single resource-specific permission for publishing, rollback, candidate/canary control, publication-mode switches, and automatic-update input selection on a Deployment. There are no separate grants for those release operations in v1. Deployment Edit configuration covers non-serving details such as name and description, not these serving changes. Delete, Pipeline Build, and document access remain separate permissions; combined operations must satisfy all applicable checks. [ADR-0005 section 11](ADR-0005-api-enforced-tenancy-and-authorization.md#11-bound-administration-grants-and-recovery) owns the two grant levels and bounded administration. This policy still requires implementation and tests.

### 1. Give each Deployment explicit state and a stable contract

A **pointer** is a stored reference to a pipeline version, not a copy of that version’s configuration.

| Deployment state | Meaning |
| --- | --- |
| **`current`** | The version selected when a request is not assigned to an active candidate. A real Deployment starts with a current version. |
| **`candidate`** | An optional version attached for review or a canary. Attaching it starts at 0% traffic. |
| **`previous`** | The optional, designated immediate rollback target. This is one target, not an unlimited stack of earlier releases. |
| **Canary percentage** | The allocation of routing buckets to the candidate. It does not promise an exact percentage of requests. |
| **Rollout identity** | An immutable identity for the candidate rollout. Changing its percentage keeps this identity; attaching a replacement candidate creates another. |
| **Deployment revision** | A number that increases as Deployment state changes. Commands use it to detect that someone else changed the state. |
| **Publication mode** | Whether publication follows Automatic updates or Manual releases. |
| **Automatic-update binding** | The selected document/configuration inputs used by automatic updates. |
| **Publication control revision** | The revision used to invalidate publication authority captured before a mode switch. Its role is explained below. |

Targets must be **complete immutable pipeline versions in the same project** and must satisfy the endpoint’s **query contract**: the request and response behavior expected by the consuming application.

The customer application continues calling the same endpoint while an engineer changes these pointers through Studio, Inframeld’s console, or the API. This promise applies to compatible pipeline versions, not incompatible changes to the endpoint’s contract.

A version’s required **materializations**—the prepared searchable indexes bound to it—must actually be available when the release transition needs them. A historical successful build or a stale readiness display is not proof that the version can still serve now.

### 2. Support two publication modes and require a ready initial version

| Mode | How publication is authorized |
| --- | --- |
| **Manual releases** | An engineer explicitly invokes candidate, canary, promotion, rejection, or rollback commands. An authorized service client can invoke the same operations. |
| **Automatic updates** | A separately authorized document or configuration action requests a build and conditional publication of its complete, ready result. Build completion alone is not publication authority. |

Modes are reversible and belong to the **Deployment**, not globally to its pipeline. Two Deployments of the same pipeline can use different modes.

The default onboarding path starts in **Automatic updates**. An explicitly created Deployment defaults to **Manual releases**, with Automatic updates available as a creation option.

**Releases owns mode changes and all pointer transitions.** [ADR-0019](ADR-0019-default-onboarding-and-first-publication.md) owns the upload/setup experience and durable update sequence that invokes those operations.

#### Create a real Deployment only with a ready initial version

Initial creation requires one genuinely ready, same-project, contract-compatible PipelineVersion and an authorized initial decision.

Under [ADR-0005 section 11](ADR-0005-api-enforced-tenancy-and-authorization.md#11-bound-administration-grants-and-recovery), Create Deployment on the project authorizes a human to create a new Deployment with that initial serving version. Record the creator's explicit initial grants, including can-use-and-grant Manage releases on the new Deployment, in the creation transaction. Later releases require current Manage releases on that specific Deployment; creation grants no release authority elsewhere. Build and protected-input checks remain separate. For the first automatic default publication, recheck the initiating human's current Create Deployment permission with ADR-0019's existing publication guards.

Create the initial Deployment revision atomically with that version as `current`. It has **no candidate, previous target, or rollout**. There is no baseline cohort or rollback target yet.

No fictitious ready version, judge setup, or benchmark is required to make the first endpoint exist. A **benchmark** is the set of test cases used for evaluation; evaluation is not a prerequisite for this initial creation.

#### A default route can exist before its Deployment is ready

The default experience exposes a stable logical project route before the actual Deployment exists. Its binding initially holds Automatic updates and the publication control revision.

Before readiness, the route returns a **typed not-ready outcome**—a defined response the client can recognize—without generating an answer.

```text
Stable project route exists; no ready Deployment yet
    -> Authorized update invokes the ordinary Build operation
        -> A complete pipeline version becomes ready
            -> Separate conditional first-create command
                -> Create Deployment and bind the route atomically
```

First creation transfers the selected publication-control state and binds the route in the same transaction. Concurrent mode changes check the same authority; they cannot be ignored because this is the first publication.

An explicitly created Deployment instead selects an already-ready initial version directly. **Creating a Pipeline alone never makes it serve traffic.**

### 3. Keep canary assignment stable with an affinity key

A **cohort** is a group of routing identities assigned to a variant. A **variant** is the version a request actually uses: current or candidate during a canary.

An **affinity key** identifies the application’s user or session for routing. It does not authenticate that person or grant document access.

#### Authenticate first, then determine routing affinity

| Caller | Affinity input |
| --- | --- |
| **Human querying through Studio** | The stable internal human principal ID. A principal is the identity Inframeld recognizes as the caller. |
| **Customer application** | A bounded opaque `affinityKey` supplied for its end user or session, scoped to the authenticated integration principal. |

Authenticate the caller as an allowed query/service principal before routing. Human identity and scoped opaque service credentials follow ADR-0005.

Keep application affinity values opaque: do not put email addresses or other unnecessary personal data in them. **An affinity key is routing data, never verified end-user identity or permission.**

#### Calculate one deterministic bucket

For application requests, the routing inputs are:

```text
organization ID
    + project ID
    + deployment ID
    + stable integration-principal ID
    + affinityKey
    + rollout ID
```

For human requests, use the stable internal human ID as the affinity input.

Use a fixed, versioned cryptographic hash or HMAC construction and map the result to a bucket from **0 to 9,999**. HMAC is a keyed hash construction. Persist the routing algorithm identity; do not use a language runtime’s randomized hash.

The selection rule is:

```text
candidate, when bucket < canary percentage × 100
current, otherwise
```

**The percentage is not an input to the hash.** Changing the allocation moves the threshold, not the identities’ buckets.

#### Example: increase the allocation without reshuffling existing buckets

| Affinity identity | Fixed bucket | At 10%: threshold 1,000 | At 25%: threshold 2,500 |
| --- | --: | --- | --- |
| Alice | 630 | Candidate | Candidate |
| Bob | 1,850 | Current | Candidate |

Increasing the percentage includes more buckets while Alice remains in the candidate cohort.

Setting the same rollout to **0%** pauses candidate traffic without discarding its buckets. Increasing it later uses those same assignments. Replacing the candidate creates a **new rollout ID** and intentionally starts a new assignment.

#### Keep integration identity stable across credential rotation

Replacing a credential for the same integration must not reshuffle its users. The hash uses the stable integration-principal ID, not the credential itself. A newly created integration has a new scope.

When application affinity is missing while candidate traffic is enabled, return **`422 affinity_required`**. Do not put the entire application into one bucket using its credential, and do not fall back to random per-request routing. With no candidate traffic, affinity is optional.

A canary percentage describes allocation across **affinity identities**, not exact request counts. One very active user can generate most requests. Show observed counts and failures per variant, and do not claim statistical significance from a tiny cohort.

### 4. Apply the same safety checks to every release transition

Every transition requires permission, an **idempotency key**, and **`expectedRevision`**.

These values solve different problems. The idempotency key identifies a retry of the same action. The expected revision identifies the Deployment state on which the caller based that action; it prevents a different operator’s change from being overwritten.

Load the caller’s scope first, validate the requested transition, and atomically update state and audit evidence using a conditional revision check. Recheck target availability inside the transition/publication protocol rather than trusting a previously displayed status.

#### Manual-release commands

All five commands below require **Manual releases**. In Automatic updates, return a typed mode conflict instead of silently changing modes.

| Command | Effect |
| --- | --- |
| **Attach candidate B** | Keep current A. Set candidate B, create a new rollout identity, and start at **0%**. Reject an existing candidate unless it has first been explicitly aborted. |
| **Set canary percentage** | Change the candidate allocation only. Current/candidate version identities and the rollout’s bucket assignments remain fixed. |
| **Abort candidate** | Keep current and previous unchanged. Clear the candidate and its active rollout traffic. Retain build and evaluation evidence. |
| **Promote** | Set previous to current A, then current to candidate B. Clear the candidate and candidate traffic. Preserve evidence. |
| **Roll back promotion** | Restore previous A as current and clear `previous`, consuming that one-step rollback target. Retain B’s immutable evidence. |

These operations change release state, not the immutable versions or their evidence.

Reject a candidate identical to `current`. An attached candidate must be explicitly aborted before attaching another; a 0% allocation is still an attached candidate.

Changing the canary percentage does not itself promote the candidate. Promotion is a separate command, including when all traffic has been allocated to the candidate.

#### Rollback is neither candidate rejection nor an unlimited history browser

Rollback with an attached candidate returns **`409 candidate_active`**. Explicitly abort the candidate first, so one command does not unexpectedly reject a trial and undo an earlier release.

Retain only one designated immediate rollback target, including after automatic publication. Selecting an older historical version requires an explicit new candidate/release rather than traversing an unbounded rollback stack.

Rollback requires Manual releases. Switching from Automatic updates to perform it leaves Manual releases selected afterward. Re-enabling Automatic updates is a separate authorization to apply the selected inputs again; rollback success never re-enables it implicitly.

### 5. Distinguish rejection, rollback, and conflicts in worked examples

#### Reject a bad canary without undoing the current release

Start with previous Z, current A, and candidate B. B produces errors, so the engineer invokes `abort_candidate`.

```text
Before: previous Z | current A | candidate B
After:  previous Z | current A | no candidate
```

A remains current. Restoring Z would incorrectly undo A, which was not the release being tested.

#### Undo a completed promotion

Start with current A and candidate B. Promote B, then later roll it back:

```text
Before promotion: current A | candidate B
After promotion:  current B | previous A | no candidate
After rollback:   current A | no previous | no candidate
```

Rollback consumes the previous pointer; it does not put B into that slot as an automatic way to toggle back and forth. B’s immutable evidence remains inspectable, and B can later be explicitly attached as a new candidate.

#### Report an unavailable rollback target without changing current

Current is B and previous is A, but A’s required materialization is unavailable or its source was explicitly erased.

Return **`409 rollback_target_unavailable`** with safe same-project details. B remains current. Do not substitute another version or search an unfiltered corpus.

An operator may restore the missing dependency or release a different valid candidate.

#### Reject a stale command from a concurrent operator

Two operators both read Deployment revision **8**. One promotes B and commits revision **9**. The other’s command still expects revision 8 and receives **`409 stale_revision`**.

The client reloads the state and asks for a fresh decision. It must not silently replace 8 with 9 and retry the promotion against state the operator did not review.

### 6. Make automatic publication a separate guarded transition

Automatic updates uses the same ready pipeline versions and release ownership. It changes how publication is requested, not whether publication requires authorization and concurrency checks.

| Command | Preconditions and effect |
| --- | --- |
| **Switch to Manual releases** | Preserve current and previous. Advance the publication control revision and invalidate pending automatic publication. Completed external calls are not undone. |
| **Enable Automatic updates and apply pending changes** | Reject the request if any candidate is attached, including at 0%; require an explicit abort first. Freeze the displayed valid corpus/configuration, advance the control revision, and atomically admit a fresh update. Keep current until publication. If the selected inputs are already current, report up-to-date without new model work. |
| **Publish an authorized automatic update** | After all publication checks pass, set previous to current and current to the complete ready result. There is no candidate or rollout. Publishing a result identical to current is a no-op. |

The **corpus** is the selected set of source documents. Freezing the inputs means the update records exactly which corpus and configuration it is preparing; later edits do not silently change that work.

#### Check that this update still has authority to publish

Automatic publication requires all of the following to remain true:

| Check | Required state |
| --- | --- |
| **Mode** | The Deployment is still in Automatic updates. |
| **Control revision** | It still matches the revision captured by this update. |
| **Requested update** | This is still the newest requested update identity. |
| **Job ownership** | The executing job still owns the right to publish. |
| **Serving state** | It still matches the state expected by the transition. |
| **Authorization** | The initiating action remains authorized under current permissions. |
| **Dependencies** | The complete result and its required dependencies are ready. |
| **Candidate** | No candidate is attached. |

**Build completion alone never performs this publication.** Audit records distinguish automatic publication authorized by an update action from manual promotion. They retain the initiating actor and the frozen input references.

Automatic publication does not require a benchmark and must not fabricate a positive evaluation decision.

### 7. Prevent old automatic work from surviving a mode switch

The **publication control revision** records whether a pending update’s captured authority is still applicable. Every mode switch advances it.

For example:

```text
Control revision 10: automatic update J is admitted
Control revision 11: user switches to Manual releases
Control revision 12: user enables Automatic updates again
```

J still carries revision **10**. It cannot publish at revision 12 simply because the mode is automatic again.

New enablement admits a fresh request. Compatible artifacts may be reused, but the old request’s publication permission cannot be reused or rewritten to match the new revision.

#### Resolve publication-versus-switch races in PostgreSQL

Publication and switching both commit through conditional guards in PostgreSQL.

| Which commits first? | Result |
| --- | --- |
| **The mode switch** | Its changed control revision makes the old automatic publication ineligible. |
| **The automatic publication** | It advances the Deployment revision. A switch expecting the earlier revision conflicts and leaves the mode unchanged. The user reloads before deciding again. |

A successful switch preserves the **then-current version**. It does not reverse a publication that already committed, and it does not undo an external call that has finished.

[ADR-0019](ADR-0019-default-onboarding-and-first-publication.md) defines serialized updates per Deployment, the newest authorized input request, safe retries, and deletion/rebinding behavior. A **rebind** changes the target selected by a stored route or configuration binding.

There is no first-use-only publication permission and no **`everPublished`** gate. Reversible mode control replaces that restriction. Deliberate deletion still blocks old work through ordinary lifecycle markers; restarting the application does not authorize recreating a deliberately deleted Deployment.

### 8. Keep evaluation and feedback informative, not authoritative

The primary release workflow is inside Inframeld. Engineers review benchmark comparisons and observed canary behavior in Studio, then explicitly request manual release transitions.

**A higher evaluation score never authorizes promotion.** Missing, failed, or regressed evidence requires explicit acknowledgment under the existing decision contract. Promotion requires a version that can serve and a recorded operator decision.

A promotion can follow a canary or an explicit **zero-traffic review**, where the candidate was reviewed without receiving customer traffic. V1 imposes no arbitrary minimum observation period or statistical acceptance gate.

OpenEvals is selected for evaluation, and Luna is the initial configurable judge to qualify under [ADR-0008](ADR-0008-deterministic-evaluation-and-release-decisions.md). A **judge** is a model used to assess answers; qualification means testing that selected integration, not assuming it has passed.

Optional service clients invoke the same commands with their own permissions and audit identity. An external continuous-integration (CI) service is not required to own checks or approvals. ADR-0002 records the in-app action sequence.

#### Distinguish explicit decisions from work that runs automatically

| Mode | Explicit action | Work performed after admission |
| --- | --- | --- |
| **Manual releases** | Build, Compare, attach/change a candidate, change its percentage, promote, reject, or roll back are authorized actions in Studio. | Admitted work, progress tracking, safe retries, and cohort routing execute automatically. |
| **Automatic updates** | An authorized source/configuration action requests a build and conditional publication together. **Compare remains explicit.** | The ordinary build runs, followed by a separate publication attempt subject to its current guards. |

**Admission** means durably accepting the requested work. In either mode, no GitHub runner, callback, webhook, or general workflow engine is required.

#### Attribute online feedback to the answer that actually served

Answer feedback is required during canaries and **100% serving**, not only during a trial.

Use the **`AnswerReceipt`**, the record identifying a particular answer execution, to attribute feedback to its original pipeline version, Deployment revision, rollout, and cohort. A later promotion or rollback must not attach that feedback to whichever version is current when it arrives.

Show online counts and comments separately from offline benchmark results. Label the feedback denominator and coverage: the population the counts describe and how much of that population supplied feedback.

Feedback never triggers automatic release transitions. [ADR-0017](ADR-0017-answer-feedback.md) defines the detailed feedback contract.

### 9. Let in-flight queries finish without preserving revoked access

A query selects **one Deployment revision and one pipeline version once**. A request already using A may finish after B is promoted. New requests resolve the updated pointers and routing state.

Ordinary retention protects the dependencies of current, candidate, and previous versions. It also protects resources being used by an admitted query.

At query selection, admit a bounded **operation pin** atomically against the **retirement gate**. The pin records that the query is using those resources; the retirement gate coordinates this admission with cleanup so resources cannot be deleted between selection and protection.

Routine **garbage collection (GC)**—removal of data no longer needed—includes these pins and must not delete artifacts an admitted request is using. ADR-0004 defines the protocol.

**Security revocation and explicit erasure take precedence over ordinary retention.** Apply the access/deletion rules to the affected request rather than silently rerouting it to another version.

Document authorization is checked independently for whichever pipeline is selected. Moving a request into a candidate cohort never grants access to additional documents.

### 10. Verify routing, transitions, and races before release

The following are acceptance conditions, not completed test results.

| Area | Required verification |
| --- | --- |
| **Initial creation** | The first real Deployment has a ready, same-project, compatible current version and an authorized decision, with no candidate, previous target, or rollout. The default route returns not-ready without generation beforehand. |
| **Deterministic routing** | Check fixed bucket examples, identity-scoped affinity, credential-rotation stability, increasing percentages, and pausing/resuming the same rollout. |
| **Missing affinity and project scope** | Reject missing application affinity while candidate traffic is enabled. Reject cross-project targets. |
| **Manual transitions** | Distinguish abort from rollback; reject unavailable targets and stale revisions; verify the one-step rollback rule and candidate guards. |
| **Mode switching** | Test both directions, including rejection of the mode-change request when a 0% candidate is still attached. Preserve the current version and retain the correct automatic-publication rollback target. |
| **Late or competing work** | Test rapid switching with late completion, overlapping uploads, publication-versus-switch races, lost acknowledgments, and lifecycle checks after deletion or rebinding. |
| **Permissions and in-flight requests** | Exercise permission changes and query completion across promotion without losing required retention protection or bypassing current access rules. |
| **Audit and feedback** | Record the actor, selected versions, rollout/revision, decision acknowledgment, and outcome. Preserve original receipt attribution for late feedback. Do not retain raw affinity values unnecessarily. |

These checks cover the routing and transition contract, including the additional publication-mode races.

## Consequences

### Positive

- **Customer integrations stay stable across compatible releases.** Engineers can change the serving version inside Inframeld without requiring a new version-specific endpoint integration.
- **Trials and recovery have distinct, predictable effects.** Sticky routing avoids reshuffling cohorts when allocation changes. Candidate rejection preserves the working release, while rollback explicitly consumes the immediate previous target.
- **Publication stays tied to current authority.** Revision checks, update identities, readiness checks, and audit records prevent stale commands or late jobs from silently overriding newer decisions. Historical answer attribution remains unchanged.

### Negative

- **Canaries require an explicit client contract.** Customer applications must supply affinity when candidate traffic is enabled. Allocation is by identity, so observed request shares can be uneven and small cohorts do not establish statistical significance.
- **Rollback is deliberately limited.** Only one immediate previous target is designated, and it must remain usable. An active candidate must be aborted first; users in Automatic updates must switch to Manual releases before rollback.
- **Mode changes and publication require coordinated state.** Deployment and control revisions, frozen inputs, current job ownership, readiness, permissions, and retention must be checked together. Switching modes cannot reverse already-completed external work or an already-committed publication.

## Alternatives considered

No separate comparative evaluation is recorded. The following approaches are excluded by this decision.

### Randomly route every request or bucket an entire application by its credential

**Ruled out.** Use identity-scoped affinity and a deterministic, versioned routing construction. Credential rotation must not reshuffle an integration’s users. Missing required affinity is an error, not permission to invent another assignment method.

### Treat candidate rejection and rollback as the same action

**Ruled out.** Aborting B while A is current must preserve A and its previous target. Rolling back a completed promotion restores the designated previous version and consumes that pointer. Combining both actions would obscure which release the operator intended to undo.

### Maintain an unlimited rollback stack

**Not selected.** Keep one designated immediate rollback target. Selecting older history requires an explicit new candidate/release, with the normal availability and permission checks.

### Publish on build completion or automatically follow evaluation scores and feedback

**Ruled out.** Build readiness is not publication authority, and neither scores nor ratings authorize a transition. Automatic updates uses a separately authorized update action and a guarded publication command; Manual releases uses explicit operator decisions.

### Allow automatic publication only once during onboarding

**No longer part of the design.** Publication modes are reversible. There is no first-use-only permission or `everPublished` gate. Control revisions and ordinary lifecycle markers invalidate stale work without prohibiting later authorized automatic updates.

### Require an external CI runner or workflow engine to own releases

**Not required.** Studio and authorized API clients use Inframeld’s own application operations. Durable execution, progress, safe retries, and routing do not require a GitHub runner, callback, webhook, or general workflow engine.

## References

| Reference | Responsibility |
| --- | --- |
| ADR-0002 | The accepted in-app build, comparison, canary, and release sequence. |
| ADR-0004 | Query pins, the retirement gate, and retention of resources used by in-flight requests. |
| ADR-0005 | Kratos human identity, scoped opaque service credentials, and document authorization. |
| [ADR-0007: Idempotency](ADR-0007-durable-jobs-idempotency-and-recovery.md) | Durable jobs, idempotency, safe retry behavior, and competing state changes. |
| [ADR-0008: Evaluation](ADR-0008-deterministic-evaluation-and-release-decisions.md) | Benchmark comparisons, OpenEvals, the configurable Luna judge, and explicit decision evidence. |
| [ADR-0015: Materializations](ADR-0015-profile-specific-index-materializations-and-pipeline-bindings.md) | Complete, ready materializations and immutable pipeline bindings. |
| [ADR-0017: Answer feedback](ADR-0017-answer-feedback.md) | Receipt-based feedback attribution and its record/API contract. |
| [ADR-0019: Default onboarding and publication](ADR-0019-default-onboarding-and-first-publication.md) | Initial setup, serialized automatic updates, publication control, and deletion/rebinding behavior. |
