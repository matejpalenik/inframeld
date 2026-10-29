# Submit and correct feedback on an answer

<a id="submit-and-correct-feedback-on-an-answer"></a>

SupportBot rates answer A77 after Production has changed versions. The rating belongs to the original answer receipt and principal. A retry recovers the original edit, while a fresh read reports the current rating.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="store-one-current-rating-not-a-stream-of-votes"></a>

### Store one current rating, not a stream of votes

Store one current `Feedback` record for each answer and its originating principal. It contains the rating (`positive` or `negative`), optional plain-text comment, integer revision, creation/update timestamps, and attributable submitting principal.

Feedback refers to the original receipt to establish which version produced the answer. **Never attribute it to the version selected by the Deployment's `current` pointer today.**

Credential rotation preserves the stable principal and therefore its feedback ownership. A credential for a different integration does not inherit another integration’s rights.

Editing replaces the current rating and comment. Keep the normal minimal audit record, without a feedback event stream or indefinite copies of every old comment. Counts use the latest rating, not the number of requests or edits.

CLI v1 reporting and own-answer corrections use these same records under CLI feedback capability. They create no CLI-owned feedback store, do not transfer receipt ownership between accounts, and cannot add direct-query/evaluation executions to live coverage. Reporting authority remains separate from permission to change an originating principal's own rating.

A unique answer/originating-principal pair prevents duplicate ratings even after request-deduplication history expires. A receipt proves the response was produced, not that someone saw it. It keeps no full production question, answer, or final-context text. A caller-supplied end-user ID creates neither another principal nor an extra vote.

[Feedback](./answer-feedback.md) owns creation/editing, authorization, retention, and denominators. [Jobs](answer-execution-and-receipts.md#answers) owns receipt-only recovery after a lost response. Later release changes never reattribute a receipt or its feedback.

<a id="attribute-online-feedback-to-the-answer-that-actually-served"></a>

### Attribute online feedback to the answer that actually served

Answer feedback is required during canaries and **100% serving**, not only during a trial.

CLI feedback capability delivers authorized reporting and own-answer rating/correction through CLI v1. Deferred Studio consumes the same backend operations. Separate reporting authority never permits editing another originating principal's rating, and the CLI does not prompt for a rating after every query by default.

Feedback uses the AnswerReceipt's original version, Deployment revision, rollout, and routing group. A later promotion or rollback cannot move it to the version current when the rating arrives.

Show online feedback separately from offline results. Explain which answers the counts cover and how many of those answers received a rating.

Feedback never triggers automatic release transitions. [Understanding feedback on answers](./answer-feedback.md) defines the detailed feedback contract.

<a id="start-with-an-answer-receipt"></a>

## Apply accepted PD-KNOWLEDGE-02

Accepted [PD-KNOWLEDGE-02](../../inframeld-knowledge/references/decision-retention-erasure-policy.md#approved-resolution) selects this workflow's detailed contract. Keeping everything forever eventually exhausts the host and makes erasure harder. Finite defaults make normal growth predictable, while safety obligations cannot be discarded just because a timer expired. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## Start with an answer receipt

An **AnswerReceipt** records that an eligible response was produced, who requested it, the version and release context used, and all supporting sources. It does not store the full answer or prove anyone saw it. Pipelines saves the completed receipt before returning the response.

Each answer and its originating principal have one current rating. A **principal** is the stable identity of the human or application that requested it. Editing a rating changes that record rather than adding another vote.

Under [shared current connectivity](../../inframeld-application-contracts/references/model-connection-changes.md#shared-current), two answers from the same PipelineVersion may have used different connection access revisions. Preserve safe actual connection/model observations with execution/receipt attribution, independently of optional diagnostic tracing. Feedback remains attached to its original answer and serving version. Never relabel it with the connection's current settings. Version-level reports may combine those environments and must disclose that limitation rather than imply identical execution conditions. This does not add a new feedback dimension or change rating/coverage arithmetic. Direct-query/evaluation still stay outside production feedback.

<a id="keep-ownership-with-the-existing-application-modules"></a>

### Keep ownership with the existing application modules

| Owner | Responsibility |
| --- | --- |
| **Pipelines** | Owns serving responses, their `AnswerReceipt` records, and answer feedback. Records the release selection supplied at query admission. |
| **Releases** | Owns Deployment transitions and the cohort selection made when a query is admitted. Feedback cannot change its serving pointers. |
| **Evaluation** | Continues to own offline benchmark results. A benchmark is a set of test cases, not the production feedback population. |
| **CLI v1 and future Studio** | Read authorized projections that combine receipts, feedback, and release history. Submit explicit own-answer changes through the same backend operation. Neither is another source of truth. |

**Admission** means accepting a query to run. A **read projection** combines existing records into a useful view. Displaying records together does not give a client ownership of their changes.

<a id="submit-edit-and-read-a-rating"></a>

<a id="operation"></a>

<a id="2-submit-edit-and-read-a-rating"></a>

## Submit, edit, and read a rating

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

<a id="read-the-current-state-after-a-conflict-or-lost-response"></a>

### Read the current state after a conflict or lost response

Use the same resource path for reads:

```text
GET /v1/projects/{projectId}/answers/{answerId}/feedback
```

The originating principal may read its current rating, comment, and revision while still passing the receipt, project, and evidence checks. `feedback:write` includes this narrow read of its own feedback. It does not open the project-wide report in any client.

For example, after a lost edit response, the customer application can fetch the actual current revision instead of guessing which number to send next.

<a id="distinguish-a-retried-command-from-a-competing-edit"></a>

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

<a id="replaying-an-edit-is-different-from-reading-current-feedback"></a>

### Replaying an edit is different from reading current feedback

Suppose the first rating created revision `1`, then an edit created revision `2`. Retrying the first command can return its original success at revision `1`. That describes the original command's result, not the current rating.

An authorized GET returns the current rating. This lets a client recover what an earlier command did without making another edit.

A database uniqueness rule allows only one record per answer and principal. It still prevents a second initial vote after the request's idempotency record expires.

<a id="check-the-caller-and-bound-evidence"></a>

<a id="authorization"></a>

<a id="feedback-authority"></a>

<a id="3-check-the-caller-and-bound-evidence"></a>

## Check the caller and bound evidence

New human Project creators receive explicit `inspect-feedback`, and new Deployment creators receive explicit `feedback:write`, through [fixed creator assignments](../../inframeld-access-models/references/actions-and-initial-grants.md#initial-assignments). Existing resources are not backfilled. These revocable grants do not permit editing another principal's rating or bypass current Query/receipt/evidence checks.

An integration needs both `query` and the separate `feedback:write` permission on the exact Deployment to submit feedback. Existing query credentials do not gain feedback permission automatically. [Access](../../inframeld-access-models/references/actions-and-initial-grants.md#reviewed-capability-catalogue) records the accepted identifiers/targets. Applications receive use only. Rotating an application key preserves the originating principal and therefore own-rating identity.

| Caller and operation | Required access |
| --- | --- |
| **Integration submitting or editing feedback** | The same stable principal that originated the receipt, `query` and `feedback:write`, current project access, and current access to the bound evidence. |
| **Originating principal reading its own feedback** | The narrow own-feedback permission included in `feedback:write`, with the same receipt, project, and evidence checks. |
| **Human querying a live Deployment through CLI or Studio** | May rate their own eligible live serving receipt, subject to the applicable current permissions. This does not include protected direct Pipeline queries or offline evaluation executions. |
| **Direct Pipeline query or evaluation execution** | Not eligible for production feedback, even if the caller can also query the live Deployment. Direct-query evidence is inspected through its own authorized workflow. |
| **Human or application inspecting project-wide feedback through CLI or future Studio** | `inspect-feedback` on the exact Project and current access to the evidence involved. The reader need not be the originating principal of each answer, but cannot edit those principals' ratings. Reporting returns only the currently authorized evidence subset. |

Access owns default permissions and onboarding assignments. Feedback reuses its rules rather than choosing new defaults or adding another permission evaluator.

<a id="keep-the-integration-credential-in-the-customers-backend"></a>

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

<a id="filter-comments-and-totals-using-current-server-side-policy"></a>

### Filter comments and totals using current server-side policy

Check current access to every source behind the receipt before returning it or its comment. A comment may quote private source text even though Inframeld never stored the answer.

Apply the same access rules to records and totals. Otherwise a count could reveal hidden feedback. Label report totals as the **visible authorized subset** in human and machine output.

The backend filters SQL reads and aggregate calculations through the existing Access policy. It must not send all feedback to a client and rely on that client to hide it.

An explicit insufficient-evidence answer can have no source evidence to check. Project and action permissions still apply. Submitting feedback or reading one's own receipt requires ownership. A project-feedback reader instead needs the separate inspection authority.

<a id="keep-attribution-and-expiry-together"></a>

<a id="lifecycle"></a>

<a id="4-keep-attribution-and-expiry-together"></a>

## Keep attribution and expiry together

Consider this sequence:

| Time | Event |
| --- | --- |
| **10:00** | SupportBot receives answer **A77** from **P13**, the **10% candidate** in rollout **C4**, at Deployment revision **42**. |
| **10:05** | Alice rejects P13. New requests go to P12. |
| **10:20** | The user rates A77 negative through SupportBot. |

The negative rating belongs to **P13 / C4 / revision 42**, which produced A77. P12 being current at 10:20 does not make it P12's rating.

Promotion and rollback also leave the attribution unchanged. A query accepted before a release may finish afterward and still belongs to its original selection. A release change alone does not expire its receipt.

Late feedback is allowed only while the receipt exists and remains accessible. Keeping its version ID is enough to identify the result. Feedback does not force the old vectors to remain stored or keep that version available for rollback.

<a id="give-feedback-the-same-bounded-lifetime-as-its-receipt"></a>

### Give feedback the same bounded lifetime as its receipt

The receipt and feedback share one configured lifetime. Expose the expiry time. The initial duration is an implementation default still to document, not permission to retain feedback forever.

| Lifecycle event | Required behavior |
| --- | --- |
| **Receipt expires or is purged** | Its feedback and comment expire or are purged with it. |
| **Project deletion or relevant source erasure** | Remove or redact affected feedback under [Keeping and deleting data deliberately](../../inframeld-knowledge/references/deletion-and-retention.md). A tombstone blocks access before asynchronous cleanup finishes. |
| **Ordinary permission revocation** | Prevent viewing and new submissions without necessarily deleting the project-owned feedback record. |
| **Deployment transition while the receipt remains eligible** | Preserve the original attribution and allow currently authorized feedback within the existing window. |

A **tombstone** is a saved deletion marker that blocks access before cleanup finishes. Comments must not survive in a form that reveals evidence erased with their receipt or source.

Feedback does not add production questions, answer bodies, or full retrieved text to receipts. CLI and future Studio can show the rating, comment, version, time, release context, and permitted citation IDs. They cannot replay the original answer text. A customer needing that text keeps its successful response.

Offline evaluation saves limited-size answers and evidence for comparison. That separate purpose does not allow production-answer logging here.
