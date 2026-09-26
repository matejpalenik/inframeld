# Understanding feedback on answers

SupportBot receives answer A77 from Production and rates it later. Production may have changed by then, but the rating must still describe the version that answered A77. This guide follows that rating through creation, editing, access checks, and reporting.

Start with [how an answer is served](pipelines-and-releases.md#serving). The [Pipelines records](data-model.md#pipelines) define receipts and feedback, and [Access](access-control.md) defines current permissions.

Sections 1–3 explain recording and changing a rating. Sections 4–5 explain what happens after a release, lost access, or expiry, and how to read the resulting counts.

> **Design status:** This is the accepted v1 feedback contract. Endpoints, storage, UI, and the behavioral tests below still need implementation and verification.

## Contents

| Reader’s question | Start here |
| --- | --- |
| Who owns feedback? | [1. Start with an answer receipt](#model) |
| How does a client recover the current state? | [2. Submit, edit, and read a rating](#operation) |
| Who may submit or inspect feedback? | [3. Check the caller and bound evidence](#authorization) |
| What happens after a release or deletion? | [4. Keep attribution and expiry together](#lifecycle) |
| What does a feedback percentage mean? | [5. Read counts honestly](#reporting) |
| Which cases must remain correct? | [6. Maintainer checks](#maintainer-checks) |
| Why these choices, and what remains open? | [7. Decision and reference map](#decision-map) |

<a id="model"></a>

## 1. Start with an answer receipt

An **AnswerReceipt** records that an eligible response was produced, who requested it, the version and release context used, and all supporting sources. It does not store the full answer or prove anyone saw it. Pipelines saves the completed receipt before returning the response.

Each answer and its originating principal have one current rating. A **principal** is the stable identity of the human or application that requested it. Editing a rating changes that record rather than adding another vote.

### Keep ownership with the existing application modules

| Owner | Responsibility |
| --- | --- |
| **Pipelines** | Owns serving responses, their `AnswerReceipt` records, and answer feedback. Records the release selection supplied at query admission. |
| **Releases** | Owns Deployment transitions and the cohort selection made when a query is admitted. Feedback cannot change its serving pointers. |
| **Evaluation** | Continues to own offline benchmark results. A benchmark is a set of test cases, not the production feedback population. |
| **Studio** | Reads authorized projections that combine receipts, feedback, and release history. It is not another source of truth. |

**Admission** means accepting a query to run. Studio's **read projection** combines existing records into a useful view. Displaying records together does not give Studio ownership of their changes.

<a id="operation"></a>

## 2. Submit, edit, and read a rating

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

The idempotency key lets the backend recognize a repeated command. `expectedRevision` is the feedback record's change number, **not the Deployment revision** in the receipt.

| Requested action | Required revision and result |
| --- | --- |
| **Create the first rating** | Send `expectedRevision: 0`. Success returns a safe Feedback DTO with revision `1`. A DTO is the structured data returned by the API. |
| **Deliberately edit that rating/comment** | Send a new command/key with `expectedRevision: 1`. Success atomically replaces the current values and returns revision `2`. Later edits follow the same rule. |
| **Clear the comment** | Omit `comment` or send an empty comment. The rating is still required. Omitting the comment does not mean “keep the old comment.” |

Comments are limited to **2,000 Unicode code points**. Also enforce a request-byte limit because text length and encoded size differ. The numerical byte limit remains to be chosen.

Show comments as escaped plain text. They are never trusted HTML or instructions to execute. V1 needs no separate comment feed or feedback-deletion workflow, but normal expiry and erasure still apply.

### Read the current state after a conflict or lost response

Use the same resource path for reads:

```text
GET /v1/projects/{projectId}/answers/{answerId}/feedback
```

The originating principal may read its current rating, comment, and revision while still passing the receipt, project, and evidence checks. `feedback:write` includes this narrow read of its own feedback. It does not open Studio's project-wide list.

For example, after a lost edit response, the customer application can fetch the actual current revision instead of guessing which number to send next.

### Distinguish a retried command from a competing edit

Two safeguards solve different problems. An idempotency key recognizes a retry of the same edit. A revision detects another edit that happened meanwhile. Both are required.

| Situation | Behavior |
| --- | --- |
| **Same idempotency key and same request** | After current authorization, replay the safe original mutation result. Do not add another rating. |
| **Same key, changed rating/comment** | Return **`409 idempotency_key_reused`**. A deliberate change requires a new command/key. |
| **Two different commands use the same expected revision** | One commits. The other receives **`409 stale_revision`**. Reload before making a fresh decision. |
| **A new key tries to create a second initial rating** | Conflict with the existing resource. The answer still contributes one current rating. |
| **A deliberate edit supplies the current revision** | Replace the rating/comment atomically and increment the revision. |
| **Receipt expired, purged, outside the caller’s scope, or otherwise inaccessible** | Return the API’s non-enumerating unavailable/not-found response. Do not reveal the answer or an earlier rating. |

A **non-enumerating response** gives no clue whether an inaccessible answer or rating exists. Knowing an ID is not permission to inspect it.

### Replaying an edit is different from reading current feedback

Suppose the first rating created revision `1`, then an edit created revision `2`. Retrying the first command can return its original success at revision `1`. That describes the original command's result, not the current rating.

An authorized GET returns the current rating. This lets a client recover what an earlier command did without making another edit.

A database uniqueness rule allows only one record per answer and principal. It still prevents a second initial vote after the request's idempotency record expires.

<a id="authorization"></a>

## 3. Check the caller and bound evidence

An integration needs both `query` and the separate `feedback:write` permission to submit feedback. Existing query credentials do not gain feedback permission automatically.

| Caller and operation | Required access |
| --- | --- |
| **Integration submitting or editing feedback** | The same stable principal that originated the receipt, `query` and `feedback:write`, current project access, and current access to the bound evidence. |
| **Originating principal reading its own feedback** | The narrow own-feedback permission included in `feedback:write`, with the same receipt, project, and evidence checks. |
| **Human rating a Studio test-query response** | May submit for their own eligible Studio test-query receipt, subject to the applicable current permissions. This is distinct from an offline evaluation execution. |
| **Engineer inspecting project-wide feedback in Studio** | An explicit Studio feedback-read action permission and current access to the evidence involved. The reader need not be the originating principal of each answer. |

Access owns default permissions and onboarding assignments. Feedback reuses its rules rather than choosing new defaults or adding another permission evaluator.

### Keep the integration credential in the customer’s backend

The customer application uses this path:

```text
End-user browser
    -> Customer application's authenticated backend
        -> Inframeld API: fixed integration credential + answerId + rating/comment
```

The customer backend keeps its integration key secret, checks whether its own user may access the answer, and protects the feedback route from forged or abusive requests.

Inframeld verifies SupportBot, not a claimed human behind it. Knowing `answerId` gives no access by itself. An optional display name from the application would remain unverified and is unnecessary in v1.

If Alice and Bob both use SupportBot, both act through the same application permissions. Inframeld cannot prove who clicked a rating, enforce one vote per real human, or prevent an authorized but compromised bot from submitting dishonest feedback.

Do not give the bot extra document access because its UI appears to hide private answers. This feedback path does not authenticate delegated human users.

### Filter comments and totals using current server-side policy

Check current access to every source behind the receipt before returning it or its comment. A comment may quote private source text even though Inframeld never stored the answer.

Apply the same access rules to records and totals. Otherwise a count could reveal hidden feedback. Label Studio's totals as the **visible authorized subset**.

The backend filters SQL reads and aggregate calculations through the existing Access policy. It must not send all feedback to the browser and rely on the browser to hide it.

An explicit insufficient-evidence answer can have no source evidence to check. Project and action permissions still apply. Submitting feedback or reading one's own receipt requires ownership. A Studio project-feedback reader instead needs the explicit feedback-read permission.

<a id="lifecycle"></a>

## 4. Keep attribution and expiry together

Consider this sequence:

| Time | Event |
| --- | --- |
| **10:00** | SupportBot receives answer **A77** from **P13**, the **10% candidate** in rollout **C4**, at Deployment revision **42**. |
| **10:05** | Alice rejects P13. New requests go to P12. |
| **10:20** | The user rates A77 negative through SupportBot. |

The negative rating belongs to **P13 / C4 / revision 42**, which produced A77. P12 being current at 10:20 does not make it P12's rating.

Promotion and rollback also leave the attribution unchanged. A query accepted before a release may finish afterward and still belongs to its original selection. A release change alone does not expire its receipt.

Late feedback is allowed only while the receipt exists and remains accessible. Keeping its version ID is enough to identify the result. Feedback does not force the old vectors to remain stored or keep that version available for rollback.

### Give feedback the same bounded lifetime as its receipt

The receipt and feedback share one configured lifetime. Expose the expiry time. The initial duration is an implementation default still to document, not permission to retain feedback forever.

| Lifecycle event | Required behavior |
| --- | --- |
| **Receipt expires or is purged** | Its feedback and comment expire or are purged with it. |
| **Project deletion or relevant source erasure** | Remove or redact affected feedback under [Keeping and deleting data deliberately](retention-and-deletion.md). A tombstone blocks access before asynchronous cleanup finishes. |
| **Ordinary permission revocation** | Prevent viewing and new submissions without necessarily deleting the project-owned feedback record. |
| **Deployment transition while the receipt remains eligible** | Preserve the original attribution and allow currently authorized feedback within the existing window. |

A **tombstone** is a saved deletion marker that blocks access before cleanup finishes. Comments must not survive in a form that reveals evidence erased with their receipt or source.

Feedback does not add production questions, answer bodies, or full retrieved text to receipts. Studio can show the rating, comment, version, time, release context, and permitted citation IDs. It cannot replay the original answer text. A customer needing that text keeps its successful response.

Offline evaluation saves limited-size answers and evidence for comparison. That separate purpose does not allow production-answer logging here.

<a id="reporting"></a>

## 5. Read counts honestly

Studio's Feedback panel belongs in the Pipeline or Deployment view. It offers a time range, version filter, current or previous rollout selection, positive and negative counts, total currently rated answers, and paginated comments.

During a canary, show the two groups of requests that actually received each version side by side. Include request counts, failures, latency, and a link to the separate offline comparison. The panel also works when one version serves **100%** of traffic.

### Group by answer creation time, not feedback arrival time

Default the panel’s time range to **answer creation time**. Show feedback submission/update time separately in each row.

A coverage percentage must compare ratings and eligible answers from the same population. A rating submitted today for yesterday's answer belongs with yesterday's answers. Do not divide today's incoming ratings by today's answer count.

### Count current rated answers, not submissions or people

Use the same permissions, resource scope, rollout group, and answer-time window for every count:

```text
Total current rated answers = positive answers + negative answers

Feedback coverage = unique rated answers / eligible completed serving receipts
```

Show both numbers behind coverage, not just the percentage. A retry adds no vote. Editing negative to positive moves that answer between counts without increasing the number of rated answers.

Coverage counts produced responses, not confirmed views. Unrated answers have no positive or negative verdict. Offline evaluations, failed requests, and uncertain outcomes are not eligible completed production answers.

If part of the window has missing or expired receipts or totals, label coverage **partial or unavailable**. Do not invent the missing denominator.

People choose whether to rate, and a small sample may not represent everyone. Show counts before percentages, avoid unsupported claims of statistical significance, and never use feedback to publish a release automatically.

### Worked example: eight ratings do not describe every answer

Suppose more of P13's offline answers were judged supported by their evidence, giving it a better groundedness rate. Its online ratings could still look like this:

| Observation | Count or calculation |
| --- | --- |
| **Eligible completed responses** | 100. |
| **Current rated answers** | 8. |
| **Negative ratings** | 6. |
| **Positive ratings** | 2. |
| **Feedback coverage** | 8 / 100 = **8%**. |
| **Negative share among rated answers** | 6 / 8 = **75% of rated answers**, not a failure rate across all responses. |

The other 92 responses have no feedback verdict. Alice reviews comments and benchmark regressions before deciding whether to release. The online sample and offline scores are separate observations, not a combined automatic decision.

<a id="maintainer-checks"></a>

## 6. Maintainer checks

The following are minimum implementation checks, not completed tests:

| Area | Required verification |
| --- | --- |
| **Receipt lifecycle** | Exercise crashes around query admission and finalization. Only successfully finalized eligible receipts accept feedback. Explicit insufficient-evidence responses remain labelled and eligible. |
| **Identity and scope** | Reject forged, cross-project, and other-principal answer IDs. Test credential rotation and revocation without changing ownership or accepting unverified end-user identity. |
| **Edits and retries** | Exercise duplicate commands, concurrent edits, stale revisions, lost update responses, and attempts at a second initial rating. Counts remain based on one current record. |
| **Late feedback** | Test submission after candidate abort, promotion, and rollback, preserving the original selected version and release context. |
| **Current access** | Recheck document access for submission, detail, receipt reads, replay, and aggregate totals. Include uncited final-context sources and evidence-free abstentions. |
| **Retention and deletion** | Expire and purge receipts, apply project/source deletion, and confirm affected feedback disappears or is redacted without leaking through comments or counts. |
| **Rendering and bounds** | Enforce comment/request bounds and render comments as escaped text. |
| **Studio and calculations** | Verify exact denominators, answer-creation windows, partial/unavailable coverage, and operation at 100% serving as well as during a canary. |
| **Side effects and storage** | Confirm feedback never stores full production responses, repeats model work, or moves release pointers. |

The contract defines what the implementation must demonstrate. This documentation does not claim those tests have run.

<a id="decision-map"></a>

## 7. Decision and reference map

The request-byte limit and initial receipt/feedback lifetime remain implementation choices. The 2,000-code-point comment limit is settled. [Retention](retention-and-deletion.md) governs expiry and erasure, and [jobs](jobs-and-idempotency.md) governs retries. A rating is neither release authority nor proof of a verified human vote.

| Decision | Rationale |
| --- | --- |
| [ADR-0028](../adr/ADR-0028-recover-answer-requests-through-receipts-without-a-full-answer-replay-cache.md) | Recover answer requests through receipts without a full-answer replay cache. |
| [ADR-0043](../adr/ADR-0043-keep-one-current-feedback-rating-per-answer-and-originating-principal.md) | Keep one current feedback rating per answer and originating principal. |
