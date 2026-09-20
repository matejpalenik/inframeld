# ADR-0017: Answer feedback tied to the response that was served

**Status:** Accepted — feedback contract; implementation qualification pending. **Date:** 19 September 2026. **Required approach:** One editable current rating per answer and originating principal, attributed through the original answer receipt and protected by current permissions. **Source:** [Canonical architecture guide](../ARCHITECTURE.md). **Related:** [Access](ADR-0005-api-enforced-tenancy-and-authorization.md), [receipts and retries](ADR-0007-durable-jobs-idempotency-and-recovery.md), [evaluations](ADR-0008-deterministic-evaluation-and-release-decisions.md), [releases](ADR-0009-sticky-logical-canary-deployments.md), [retention](ADR-0014-data-retention-deletion-and-external-processing.md).

## Context

Customer applications need to collect positive or negative feedback on answers produced by Inframeld, optionally with a written explanation. Engineers need to inspect that feedback in **Studio**, Inframeld’s console, both during a canary and when one version serves all traffic.

A **pipeline version** defines the behavior used to retrieve evidence and generate an answer. A **Deployment** is the serving target that selects a version. A **canary** tries a candidate version with a portion of traffic while the current version serves the rest. The selected routing group is the answer’s **cohort**.

Feedback can arrive after that selection has changed. An answer produced by a rejected candidate still belongs to that candidate, not to the version currently serving new requests.

From first principles, **feedback needs to identify what produced the answer, who may rate it, and which answers its statistics describe**. Keeping those facts separate prevents late feedback from being misattributed, retries from becoming extra votes, and incomplete feedback from being presented as a result for every answer.

## Decision

**Extend the existing bounded `AnswerReceipt` with one current positive or negative rating and an optional comment. Permit deliberate edits, enforce ownership and current evidence access, and show the results in a small Studio Feedback panel.**

An **answer receipt** records the origin and completion outcome of a serving response without retaining its full question, answer, or retrieved context. Feedback refers to that record rather than looking up the Deployment’s current version when the rating arrives.

Online feedback and offline evaluations remain separate evidence. Neither automatically changes a Deployment. This design adds no service, identity mechanism, or general analytics subsystem. Its contract is accepted; implementation tests are still required.

### 1. Keep ownership with the existing application modules

| Owner | Responsibility |
| --- | --- |
| **Pipelines** | Owns serving responses, their `AnswerReceipt` records, and answer feedback. Records the release selection supplied at query admission. |
| **Releases** | Owns Deployment transitions and the cohort selection made when a query is admitted. Feedback cannot change its serving pointers. |
| **Evaluation** | Continues to own offline benchmark results. A benchmark is a set of test cases, not the production feedback population. |
| **Studio** | Reads authorized projections that combine receipts, feedback, and release history. It is not another source of truth. |

**Admission** means accepting a query for execution. A **read projection** is a view of existing records shaped for a screen or API response. Joining records for display does not transfer ownership of those records.

### 2. Record the actual serving selection before accepting feedback

The receipt preserves both the selected version and the circumstances of its selection. A candidate can produce an answer without ever becoming the Deployment’s current version.

| Receipt information | Purpose |
| --- | --- |
| **Server-generated, unpredictable `answerId` and operation identity** | Identify the response and its originating operation. |
| **Organization/project and originating stable principal** | Establish ownership and access scope. A principal is the verified human or application identity recognized by Inframeld. |
| **Pipeline-version identity** | Identify the exact version that produced the response. |
| **Deployment identity and revision** | Record which serving target and state selected that version. |
| **Rollout identity and actual cohort** | Preserve the particular canary assignment. The rollout may be absent when there is no canary. |
| **Creation time, completion outcome, and expiry** | Establish when the response originated, how execution finished, and how long the receipt remains eligible and retained. |
| **Bounded identities of every document/version used in final generation context** | Support current access checks, including for sources that were used but not cited. |

The **final generation context** is the evidence supplied to the model to generate the answer. Its source identities matter even when the model omits some of them from its citations: a later comment may quote that uncited material.

#### Reserve the identity at admission; finalize before releasing the response

```text
Admit query and reserve answer identity
    -> Record the selected version and release context
        -> Execute the query
            -> Finalize its safe completion outcome
                -> Release the completed response
```

Only a successfully finalized, eligible serving receipt accepts feedback.

| Execution outcome | Feedback treatment |
| --- | --- |
| **Successfully completed answer** | Eligible while the receipt is retained and currently accessible. |
| **Completed explicit insufficient-evidence response** | Eligible and labelled as insufficient evidence. This is a deliberate completed response, not a provider failure. |
| **Provider failure or uncertain operation** | Not an answer to rate. |
| **Offline evaluation execution** | Does not enter the production feedback denominator. |

#### A receipt does not prove that someone saw the answer

The first serving response returns `answerId` with the answer, citations, and safe selected-version metadata.

A retry follows [ADR-0007](ADR-0007-durable-jobs-idempotency-and-recovery.md): it may return the receipt with **`responseAvailable: false`**, but it cannot recover the answer body or call the model again.

**The receipt proves that Inframeld produced a completed response. It does not prove that the customer application displayed it or that a particular human read it.** Feedback coverage must reflect that limitation.

### 3. Store one current rating, not a stream of votes

Store one current `Feedback` record for each answer and its originating principal. It contains the rating (`positive` or `negative`), optional plain-text comment, integer revision, creation/update timestamps, and attributable submitting principal.

The record references the original receipt for its provenance—the recorded origin of the answer. **Never attribute feedback by reading whichever pipeline the Deployment’s `current` pointer selects later.**

Credential rotation preserves the stable principal and therefore its feedback ownership. A credential for a different integration does not inherit another integration’s rights.

A deliberate edit replaces the current rating/comment. Keep the normal minimal mutation audit, but do not create a feedback event stream or preserve every previous comment body indefinitely. Counts reflect the latest rating, not every request, retry, or change.

#### One application-owned rating is not one vote per human

No caller-supplied end-user ID is required or treated as identity. One answer has one current rating under its originating application’s authority.

If an application shares one answer with several people, it must decide how to represent their feedback in that rating. A future multi-rater design would need an explicit identity/trust and counting contract. It is not implemented by accepting an arbitrary user ID.

### 4. Use one HTTP resource for creating, editing, and reading feedback

Create or replace feedback through:

```text
PUT /v1/projects/{projectId}/answers/{answerId}/feedback
```

Supply the normal **`Idempotency-Key`** header and this conceptual JSON body:

```json
{
  "rating": "negative",
  "comment": "The answer uses the old refund period.",
  "expectedRevision": 0
}
```

The idempotency key identifies the requested command so its retry does not execute another mutation. **`expectedRevision` is the feedback revision**, not the Deployment revision recorded in the answer receipt.

| Requested action | Required revision and result |
| --- | --- |
| **Create the first rating** | Send `expectedRevision: 0`. Success returns a safe Feedback DTO with revision `1`. A DTO is the structured data returned by the API. |
| **Deliberately edit that rating/comment** | Send a new command/key with `expectedRevision: 1`. Success atomically replaces the current values and returns revision `2`. Later edits follow the same rule. |
| **Clear the comment** | Omit `comment` or send an empty comment. The rating is still required. Omitting the comment does not mean “keep the old comment.” |

Limit the comment to **2,000 Unicode code points**, and enforce a bounded request-byte limit as well. Code-point count and encoded byte size are different measurements; both limits apply. The source contract does not specify the numerical request-byte limit.

Render comments as escaped plain text, never trusted HTML or executable instructions. The initial contract does not need a separate comment feed or feedback-deletion workflow; expiry and erasure still apply as described below.

#### Read the current state after a conflict or lost response

Use the same resource path for reads:

```text
GET /v1/projects/{projectId}/answers/{answerId}/feedback
```

The originating principal can retrieve its current rating, comment, and revision under the same receipt, project, and evidence checks. The **`feedback:write`** grant includes this narrow own-feedback read. It does not grant access to Studio’s project-wide feedback list.

This lets the customer backend or browser-facing application reload the actual state rather than guess the next revision after a conflict or lost update response.

### 5. Distinguish a retried command from a competing edit

**Idempotency recognizes the same command; revision checking prevents two different edits from unknowingly overwriting each other.** Both are required.

| Situation | Behavior |
| --- | --- |
| **Same idempotency key and same request** | After current authorization, replay the safe original mutation result. Do not add another rating. |
| **Same key, changed rating/comment** | Return **`409 idempotency_key_reused`**. A deliberate change requires a new command/key. |
| **Two different commands use the same expected revision** | One commits; the other receives **`409 stale_revision`**. Reload before making a fresh decision. |
| **A new key tries to create a second initial rating** | Conflict with the existing resource. The answer still contributes one current rating. |
| **A deliberate edit supplies the current revision** | Replace the rating/comment atomically and increment the revision. |
| **Receipt expired, purged, outside the caller’s scope, or otherwise inaccessible** | Return the API’s non-enumerating unavailable/not-found response. Do not reveal the answer or an earlier rating. |

A **non-enumerating response** avoids revealing whether an inaccessible answer or feedback record exists. Knowing its ID is not permission to inspect it.

#### Replaying an edit is different from reading current feedback

Suppose an initial command created feedback revision `1`, and a later edit produced revision `2`. Retrying the initial command may return its original successful revision `1`. That replay describes what the original command did; it does not assert that revision `1` is still current.

An authorized `GET` returns the current state. This distinction lets a client recover a mutation’s outcome without silently making another edit.

A database uniqueness constraint on **answer/principal identity** prevents duplicate records and counting even after idempotency retention expires. An expired retry record does not allow a second initial rating to become another vote.

### 6. Authorize the application and its evidence, not an alleged end user

An integration needs the dedicated **`feedback:write`** grant in addition to its serving **`query`** grant. Do not silently add feedback privileges to existing query credentials.

| Caller and operation | Required access |
| --- | --- |
| **Integration submitting or editing feedback** | The same stable principal that originated the receipt, `query` and `feedback:write`, current project access, and current access to the bound evidence. |
| **Originating principal reading its own feedback** | The narrow own-feedback permission included in `feedback:write`, with the same receipt, project, and evidence checks. |
| **Human rating a Studio test-query response** | May submit for their own eligible Studio test-query receipt, subject to the applicable current permissions. This is distinct from an offline evaluation execution. |
| **Engineer inspecting project-wide feedback in Studio** | An explicit Studio feedback-read action permission and current access to the evidence involved. The reader need not be the originating principal of each answer. |

Onboarding and default-role assignments belong to Access. Feedback does not introduce another permission engine or select those defaults.

#### Keep the integration credential in the customer’s backend

The customer application uses this path:

```text
End-user browser
    -> Customer application's authenticated backend
        -> Inframeld API: fixed integration credential + answerId + rating/comment
```

The customer backend keeps the integration credential secret, authorizes its own user’s access to the answer, and protects its feedback route against forgery and abuse.

Inframeld verifies the application, not an alleged human behind it. **An `answerId` is an identifier, not a bearer capability: possessing it does not grant access.** An optional application display label would remain unverified; v1 does not need one.

If Alice and Bob both use SupportBot, Inframeld sees SupportBot’s fixed authority. It cannot prove which person clicked a thumb, enforce one vote per real human, or prevent a compromised authorized application from submitting dishonest ratings.

Do not grant SupportBot broader document access on the assumption that its browser interface will hide restricted answers. Feedback introduces no delegated-user authentication.

#### Filter comments and totals using current server-side policy

Before returning a receipt or comment, recheck current access to all bound evidence. A comment can disclose source content even though the original answer was never stored.

Filter both individual records and aggregates to the viewer’s permitted receipt set. **Hidden comments must not leak through unfiltered counts.** Label Studio totals as the **visible authorized subset**.

Perform these checks in scoped SQL read projections using the existing Access policy, not by returning all feedback and filtering it in the browser.

An explicit insufficient-evidence response may have no bound source evidence. Project/action checks still apply. Submission and own-receipt access still require ownership; a Studio project-feedback reader instead uses the explicit feedback-read permission rather than origin ownership.

### 7. Keep late feedback attached to the original release context

Consider this sequence:

| Time | Event |
| --- | --- |
| **10:00** | SupportBot receives answer **A77** from **P13**, the **10% candidate** in rollout **C4**, at Deployment revision **42**. |
| **10:05** | Mira rejects P13. New requests go to P12. |
| **10:20** | The user rates A77 negative through SupportBot. |

**That rating belongs to P13 / C4 / revision 42.** It is not a complaint about P12 merely because P12 is current when the feedback arrives.

The same rule applies after promotion or rollback, and when a response finishes after a transition because its query was admitted earlier. Release transitions alone do not expire receipts.

Late submission remains allowed only while the receipt is retained and currently accessible. A retained version identifier is sufficient for attribution: feedback does not keep that version’s vectors stored or make it a permanent rollback target.

### 8. Give feedback the same bounded lifetime as its receipt

Use one eligibility/retention window shared by the receipt and its feedback. Configure and expose its expiry. The initial duration is an implementation default to document, not permission to retain feedback permanently.

| Lifecycle event | Required behavior |
| --- | --- |
| **Receipt expires or is purged** | Its feedback and comment expire or are purged with it. |
| **Project deletion or relevant source erasure** | Remove or redact affected feedback under ADR-0014. A tombstone blocks access before asynchronous cleanup finishes. |
| **Ordinary permission revocation** | Prevent viewing and new submissions without necessarily deleting the project-owned feedback record. |
| **Deployment transition while the receipt remains eligible** | Preserve the original attribution and allow currently authorized feedback within the existing window. |

A **tombstone** records that a resource has been deleted or retired and must no longer be accessible. Do not leave orphaned comments that disclose deleted evidence after their receipt or related source has been removed.

No production question, answer body, or full retrieved context is added to the receipt for feedback. Studio shows the rating/comment, version, time, release context, and currently authorized citation identities. **It cannot promise to replay the original answer text.** A customer application needing that text retains its own successful response.

Offline evaluation deliberately retains bounded case answers and evidence for comparison. That separate purpose does not authorize equivalent production logging.

### 9. Show feedback with matching scopes, time windows, and denominators

Add a **Feedback panel** to the pipeline/Deployment view with a time range, version filter, current/previous rollout selector, positive and negative counts, total current rated answers, and a paged comment list.

During a canary, show the two actual served cohorts side by side, alongside observed request counts, failures, latency, and a link to the separate offline comparison. The same panel works during ordinary **100% serving** without a canary.

#### Group by answer creation time, not feedback arrival time

Default the panel’s time range to **answer creation time**. Show feedback submission/update time separately in each row.

This keeps the numerator—the rated answers—and denominator—the eligible completed responses—about the same population. A late rating updates the original answer cohort. Do not divide today’s submitted ratings by today’s answers when some ratings concern answers created yesterday.

#### Count current rated answers, not submissions or people

Apply the same authorization, scope, cohort, and time-window filters to every count:

```text
Total current rated answers = positive answers + negative answers

Feedback coverage = unique rated answers / eligible completed serving receipts
```

Show both coverage counts, not just the percentage. Retries and edits do not add votes. A changed rating moves the answer between positive and negative counts; it does not create another rated answer.

Coverage describes **produced responses, not confirmed views**. Missing feedback is neither positive nor negative. Evaluation executions are not production receipts, and failed or uncertain operations are not eligible completed answers.

If receipts or totals are missing or expired for part of the window, mark coverage **unavailable or partial** instead of inventing a denominator.

A small, self-selected sample does not establish that one version is better. Show counts before percentages, avoid unsupported significance claims, and do not turn feedback into an automatic release threshold.

#### Worked example: eight ratings do not describe every answer

P13 may have a better offline groundedness rate—more evaluated answers judged supported by their context—while its online feedback shows:

| Observation | Count or calculation |
| --- | --- |
| **Eligible completed responses** | 100. |
| **Current rated answers** | 8. |
| **Negative ratings** | 6. |
| **Positive ratings** | 2. |
| **Feedback coverage** | 8 / 100 = **8%**. |
| **Negative share among rated answers** | 6 / 8 = **75% of rated answers**, not a failure rate across all responses. |

The 92 unrated responses have no feedback verdict. Mira inspects the comments and benchmark regressions before making an explicit release decision. The online sample and offline result remain distinct observations, not a combined automatic verdict.

### 10. Test admission, edits, access, and counting together

The following are minimum implementation checks, not completed tests:

| Area | Required verification |
| --- | --- |
| **Receipt lifecycle** | Exercise crashes around query admission and finalization. Only successfully finalized eligible receipts accept feedback; explicit insufficient-evidence responses remain labelled and eligible. |
| **Identity and scope** | Reject forged, cross-project, and other-principal answer IDs. Test credential rotation and revocation without changing ownership or accepting unverified end-user identity. |
| **Edits and retries** | Exercise duplicate commands, concurrent edits, stale revisions, lost update responses, and attempts at a second initial rating. Counts remain based on one current record. |
| **Late feedback** | Test submission after candidate abort, promotion, and rollback, preserving the original selected version and release context. |
| **Current access** | Recheck document access for submission, detail, receipt reads, replay, and aggregate totals. Include uncited final-context sources and evidence-free abstentions. |
| **Retention and deletion** | Expire and purge receipts, apply project/source deletion, and confirm affected feedback disappears or is redacted without leaking through comments or counts. |
| **Rendering and bounds** | Enforce comment/request bounds and render comments as escaped text. |
| **Studio and calculations** | Verify exact denominators, answer-creation windows, partial/unavailable coverage, and operation at 100% serving as well as during a canary. |
| **Side effects and storage** | Confirm feedback never stores full production responses, repeats model work, or moves release pointers. |

No application implementation or executed qualification accompanies this ADR. The accepted contract defines what the implementation must demonstrate.

## Consequences

### Positive

- **Feedback remains attached to what actually served the answer.** Late ratings keep their original version, Deployment revision, rollout, and cohort even after release transitions.
- **Users can correct feedback without inflating counts.** One current record, explicit revisions, idempotency, and database uniqueness distinguish an edit from an extra vote.
- **The feature reuses existing ownership and security boundaries.** Bounded receipts, current Access checks, existing persistence, and a small Studio view provide feedback without another service or a full production-answer archive.

### Negative

- **Studio cannot reproduce the original production answer.** The customer application must retain its successful response when it needs the text; a receipt is neither an answer replay nor proof of a human view.
- **Application-level authority limits what ratings establish.** Inframeld cannot verify individual voters, enforce one vote per person, or guarantee honest feedback from an authorized application. Shared answers require the application to choose how to represent multiple people’s responses.
- **Useful statistics require careful access and lifecycle handling.** Source permissions, expired receipts, late edits, and missing history affect visible totals and coverage. A small self-selected sample does not justify automatic release decisions.

## Alternatives considered

The following approaches are excluded or deferred by the contract. No separate comparative evaluation is recorded.

### Attribute feedback using the Deployment’s current version

**Ruled out.** The Deployment may have changed since the answer was admitted. Use the receipt’s original selected version and release context instead, including when a candidate never became current.

### Append a vote for every request or retain a complete comment-edit history

**Not selected.** Store one current rating/comment per answer and originating principal. Deliberate edits replace it, retries do not add votes, and the normal minimal audit does not become an indefinite archive of earlier comment bodies. A separate comment feed or feedback-deletion workflow is unnecessary for this initial contract.

### Treat an answer ID or supplied user ID as permission to rate

**Ruled out.** The answer ID identifies a resource; it grants no authority. Authenticate the originating principal and apply current project/evidence permissions. Verified delegation and a multi-person voting design require separate trust and counting contracts.

### Retain full production answers or vectors indefinitely for feedback

**Not selected.** Extend the bounded receipt, not the full-response logging policy. Feedback shares receipt expiry, follows source/project erasure, and does not pin vectors. Offline evaluation’s separate evidence retention does not change that production boundary.

### Use ratings as an automatic release gate or a verdict on all responses

**Ruled out.** Online feedback remains separate from offline evaluation and cannot move Deployment pointers. Report current counts and coverage for the same authorized answer population; missing feedback is not a positive or negative result.

## References

| Reference | Responsibility |
| --- | --- |
| [Canonical architecture guide](../ARCHITECTURE.md) | Overall product workflow and ownership of serving, releases, and evidence. |
| [ADR-0005: Access](ADR-0005-api-enforced-tenancy-and-authorization.md) | Verified principals, fixed integration authority, action grants, and current evidence permissions. |
| [ADR-0007: Receipts and retries](ADR-0007-durable-jobs-idempotency-and-recovery.md) | Answer-receipt lifecycle, idempotency, safe replay, and the absence of durable full-answer replay. |
| [ADR-0008: Evaluations](ADR-0008-deterministic-evaluation-and-release-decisions.md) | Separate offline benchmark results and their bounded answer/evidence retention. |
| [ADR-0009: Releases](ADR-0009-sticky-logical-canary-deployments.md) | Deployment transitions, original cohort selection, and explicit release authority. |
| [ADR-0014: Retention](ADR-0014-data-retention-deletion-and-external-processing.md) | Receipt-linked retention, current revocation, tombstones, and source/project erasure. |
