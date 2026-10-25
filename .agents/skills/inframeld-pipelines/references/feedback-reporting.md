# Read feedback reports with honest coverage

<a id="read-feedback-reports-with-honest-coverage"></a>

Alice compares feedback for current and candidate versions. Counts must describe the same authorized answer population and time window. Eight ratings do not establish what every user saw or whether the candidate should be released.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="read-counts-honestly"></a>

<a id="reporting"></a>

<a id="5-read-counts-honestly"></a>

## Read counts honestly

CLI v1 exposes a feedback report scoped to a Pipeline or Deployment. It offers a time range, version filter, current or previous rollout selection, positive and negative counts, total currently rated answers, and paginated comments. Future Studio's Feedback panel uses the same reporting contract.

During a canary, show the two groups of requests that actually received each version side by side. Include request counts, failures, latency, and a reference to the separate offline comparison. The report also works when one version serves **100%** of traffic. Keep query-operation signals distinct from the eligible-receipt feedback denominator.

Reading a report never submits a rating, calls a model or changes release state. Submitting or correcting a rating on your own answer is a separate explicit operation. Do not require a rating after each query.

Feedback commands follow the [shared CLI contract](../../inframeld-application-contracts/references/cli-result-contracts.md#cli-automation-outcomes): target/account/project overrides, bounded pages, one final JSON result by default, noninteractive inputs and descriptive dry-run. Exact command spelling and reporting schemas still need specification.

Treat comments as untrusted plain text. Escape terminal controls in human output without changing the saved comment. Machine output uses normal JSON escaping.

<a id="group-by-answer-creation-time-not-feedback-arrival-time"></a>

### Group by answer creation time, not feedback arrival time

Default the report's time range to **answer creation time**. Show feedback submission/update time separately in each row.

A coverage percentage must compare ratings and eligible answers from the same population. A rating submitted today for yesterday's answer belongs with yesterday's answers. Do not divide today's incoming ratings by today's answer count.

<a id="count-current-rated-answers-not-submissions-or-people"></a>

### Count current rated answers, not submissions or people

Use the same permissions, resource scope, rollout group, and answer-time window for every count:

```text
Total current rated answers = positive answers + negative answers

Feedback coverage = unique rated answers / eligible completed serving receipts
```

Show both numbers behind coverage, not just the percentage. A retry adds no vote. Editing negative to positive moves that answer between counts without increasing the number of rated answers.

Coverage counts produced responses, not confirmed views. Unrated answers have no positive or negative verdict. Direct Pipeline queries, offline evaluations, failed requests, and uncertain outcomes are not eligible completed production answers.

If part of the window has missing or expired receipts or totals, label coverage **partial or unavailable**. Do not invent the missing denominator.

People choose whether to rate, and a small sample may not represent everyone. Show counts before percentages, avoid unsupported claims of statistical significance, and never use feedback to publish a release automatically.

<a id="worked-example-eight-ratings-do-not-describe-every-answer"></a>

### Worked example: eight ratings do not describe every answer

Suppose P13 has a higher offline [faithfulness score](../../inframeld-evaluation/references/metrics-and-evidence.md#metrics) under the same benchmark and evaluator. That evaluation may follow earlier experiments, but only answers actually served through a live Deployment contribute online ratings. Direct Pipeline queries and evaluation executions never enter the production feedback denominator or receive a fictional live version/cohort. Their protected evidence follows [the direct-query lifecycle](direct-queries.md#preview). P13's online ratings could still look like this:

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

<a id="6-maintainer-checks"></a>

## Maintainer checks

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
| **CLI and calculations** | Verify exact denominators, answer-creation windows, partial/unavailable coverage, and operation at 100% serving as well as during a canary. Exercise human/JSON parity, bounded pagination, missing script inputs and side-effect-free dry-run. Studio qualification remains deferred. |
| **Side effects and storage** | Confirm feedback never stores full production responses, repeats model work, or moves release pointers. |

The contract defines what the implementation must demonstrate. This documentation does not claim those tests have run.

<a id="decision-and-reference-map"></a>

<a id="decision-map"></a>

<a id="7-decision-and-reference-map"></a>

## Decision and reference map

The request-byte limit and initial receipt/feedback lifetime remain implementation choices. The 2,000-code-point comment limit is settled. [Retention](../../inframeld-knowledge/references/deletion-and-retention.md) governs expiry and erasure, and [jobs](../../inframeld-application-contracts/references/jobs-and-recovery.md) governs retries. A rating is neither release authority nor proof of a verified human vote.

| Decision | Rationale |
| --- | --- |
| [ADR-0028](../../../../docs/adr/ADR-0028-recover-answer-requests-through-receipts-without-a-full-answer-replay-cache.md) | Recover answer requests through receipts without a full-answer replay cache. |
| [ADR-0043](../../../../docs/adr/ADR-0043-keep-one-current-feedback-rating-per-answer-and-originating-principal.md) | Keep one current feedback rating per answer and originating principal. |
