# Feedback, query traces and history

<a id="feedback-query-traces-and-history"></a>

SupportBot rates an answer after Production has moved to a new version. The rating still belongs to the version that produced that answer. A trace may help explain it, but trace recording, protected inspection and feedback authority are different capabilities.

<a id="feedback-follows-the-original-live-answer"></a>

## Feedback follows the original live answer

1. Resolve the exact live receipt and originating principal under current access and retention.
2. Permit one current editable rating per answer/originating principal. Correction replaces that rating rather than adding a vote.

   Use feedback's expected revision and idempotency checks, separately from the Deployment revision, so concurrent corrections do not silently overwrite one another. Reporting access never authorizes editing another principal's rating.

3. Keep version/cohort attribution from the original answer. Late feedback is not reassigned to the currently serving version.
4. Report coverage against eligible produced receipts in the same authorized answer-time window. Missing ratings are not negative votes. Shared application accounts are not proof of a human audience size.
5. Filter report totals as well as comments using current evidence access. Do not leak protected populations through aggregate counts.

CLI v1 includes authorized reporting and own-live-answer rating/correction through ordinary backend contracts. Reports cannot recover answer text from receipts or include direct-query/evaluation statistics. Backend and CLI qualification stay in the release dependency chain independently of Studio.

<a id="trace-authority-and-lifecycle"></a>

## Trace authority and lifecycle

Query on a Pipeline or Deployment does not imply query-trace inspection on that resource. Separate exact-resource inspection may include another caller's answer only with current source access. Neither resource's grant covers the other or unspecified non-query history.

Eligible humans/applications can inspect explicitly authorized traces. Project tracing/retention mutation is human-only, and explicit history deletion needs separate human deletion authority. Recording does not depend on the caller having inspection rights.

Imports may preserve destination policy. An ineligible restricted apply is denied without a saved-human fallback.

A tracing-only failure or opt-out does not cancel a healthy query, skip required accounting, authorization, receipts or audit. Separate business success from partial or unknown diagnostics.

Opt-out stops future capture and queued delivery. Re-enable applies to new admissions and cannot resume a suppressed execution. Retrying inspection or delivery never regenerates missing content.

Explicit history deletion first blocks reads, then follows durable cleanup. It never reruns model work. Automatic expiry and source erasure need no fresh human approval per record. Exact representation/fencing remains specification work rather than authority to create a tracking framework.

<a id="failure-and-presentation"></a>

## Failure and presentation

Distinguish unavailable traces, missing content, revoked access and healthy answers. CLI displays preserve actual counts, saved results, bounded protected details and human/JSON parity. A colored proposed delta does not establish a committed change. Ready build output is not a live-version change, and neutral unchanged state should stay clear.

Neither feedback nor scores change publication mode or authorize a release. Query provenance, Evaluation evidence and traces do not share a permission or retention bypass.

<a id="pending-decisions-for-dependent-implementation"></a>

## Pending decisions for dependent implementation

Before choosing an unresolved implementation contract, load only the entry whose trigger applies:

- [PD-PIPELINES-02: Make a confirmed trace opt-out stop later capture and delivery](decision-trace-policy-fencing.md). Before implementing trace capture/buffering/export delivery, opt-out acknowledgment or history-deletion fencing.

<a id="status-and-sources"></a>

## Status and sources

These are accepted product and display rules. Do not infer new storage, schemas, a diff backend or a generic operations framework from a CLI mock. Non-query diagnostics retain their explicit deferral.

- [Feedback](answer-feedback.md), [authority](answer-feedback.md#authorization), [reporting](feedback-reporting.md#reporting), [Access tracing](query-tracing-and-privacy.md#trace-authority) and [observability](query-tracing-and-privacy.md).
- [V1 scope](../../inframeld-architecture/references/v1-scope-and-extension-boundaries.md), [CLI feedback capability](https://github.com/matejpalenik/inframeld/issues/191), [non-query diagnostic deferral](query-tracing-and-privacy.md#non-query-diagnostics) and [retention/deletion](../../inframeld-knowledge/references/deletion-and-retention.md).
- [ADR-0043](../../../../docs/adr/ADR-0043-keep-one-current-feedback-rating-per-answer-and-originating-principal.md) explains one current rating. The exact catalogue and creator assignments remain with [Access contracts](../../inframeld-access-models/references/actions-and-initial-grants.md).
