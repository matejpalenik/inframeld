# Query tracing, privacy and diagnostic failure

<a id="query-tracing-privacy-and-diagnostic-failure"></a>

Alice asks a question while diagnostic storage is unavailable. If required business checks and records succeed, optional tracing failure does not fail the answer. Turning capture off and deleting saved history have different effects.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="trace-authority"></a>

<a id="trace-inspection-is-not-trace-administration"></a>

### Trace inspection is not trace administration

SupportBot may inspect a recorded answer when it has the appropriate inspection permission and is currently allowed to read the captured sources. It cannot turn recording off, change how long traces are kept or request deletion of past traces. Otherwise an automated consumer could change the history controls governing its own work.

| Action | Who may perform it? |
| --- | --- |
| Inspect pipeline traces | Humans or applications with the appropriate inspection permission and current access to the captured sources. |
| Enable or disable project tracing, or change retention | An active human with current permission to manage that project's trace policy. |
| Explicitly delete past traces | An active human with the separate permission to delete that project's trace history. Inspection or policy-management permission is not enough. |

The [reviewed catalogue](../../inframeld-access-models/references/actions-and-initial-grants.md#reviewed-capability-catalogue) selects `inspect-query-traces` on an exact Pipeline or Deployment, `manage-trace-policy` on a Project, and the separate Project `delete-trace-history`. These identifiers are accepted design, not published endpoint/schema evidence. Project tracing implements this distinction.

Inspection permission names the exact resource: a Deployment for live queries, or a Pipeline for direct queries. Neither grants inspection on the other. Inspection can reveal other callers' questions and answers on that resource, so every captured source must remain readable, including retrieved passages that were not used as final citations. Lists, stage details and JSON output obey the same checks.

Query permission, having created the resource or knowing an execution ID does not grant inspection. No pipeline permission exposes the installation's full operational trace store. The query mappings are selected. [Fixed creator assignments](../../inframeld-access-models/references/actions-and-initial-grants.md#initial-assignments) include query inspection. Product-facing non-query diagnostic browsing is [deferred in v1](#non-query-diagnostics). The tracing contract retains concrete storage/coordination/wire work.

Recording is controlled by installation constraints and project preferences, not by the caller's inspection permission. Normal retention expiry, previously authorized cleanup and source erasure use their ordinary backend permissions. They do not require fresh human approval for each record. This does not change permissions for unrelated deletion operations. A retention change must warn when existing history will expire. [Observability](#trace-authority) explains these transitions and which history a deletion affects.

CLI commands, HTTP calls and TOML imports use the same backend checks. An application can import otherwise permitted configuration while preserving destination tracing settings. If it explicitly requests a human-only change, reject that request. Do not silently omit the change or switch to a saved human login.

Check the caller's current status, permissions and reviewed state again when saving a change. If access is lost partway through an import, keep earlier completed work and report the denial for the remaining work. These are accepted rules about who may act, not evidence that the remaining contracts or runtime tests are complete.

<a id="who-may-inspect-or-change-tracing"></a>

## Apply accepted PD-PIPELINES-02

Accepted [PD-PIPELINES-02](decision-trace-policy-fencing.md#approved-resolution) selects this workflow's detailed contract. Tracing should help diagnose a query without becoming a second, uncontrolled copy of private data. A confirmed off action must affect running processes and queued writes, not just a settings screen. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## Choose a focused reading task

- For opt-out, deletion and delivery fences, read [Trace capture and deletion](trace-capture-and-deletion.md).

## Who May Inspect or Change Tracing

SupportBot can help Alice diagnose an answer when it has explicit trace-inspection permission and current access to the captured sources. That does not let it switch recording off or erase the history it is inspecting. The project tracing ticket settles this eligibility boundary. [Access](#trace-authority) owns grants and enforcement.

| Requested action | Eligible caller and required authority |
| --- | --- |
| Inspect permitted query traces | Active humans or application accounts with `inspect-query-traces` on the exact Pipeline or Deployment and current source access |
| Enable or disable project tracing | Active humans with `manage-trace-policy` on the exact Project |
| Change project trace retention | Active humans with `manage-trace-policy` on the exact Project, within operator limits |
| Explicitly delete past project traces | Active humans with separate `delete-trace-history` on the exact Project |

There is no all-powerful tracing role. Query permission, project membership or knowing a trace ID does not grant inspection. Being human does not by itself permit a policy change or deletion.

Live-query inspection names an exact Deployment. Direct-query inspection names an exact Pipeline. Neither permission grants the other, and neither introduces an Experiment resource or permission. Either can reveal other callers' questions and answers on that resource. Explain that when granting access.

Check access to every captured source, including retrieved candidates excluded from the final context. The [reviewed Access catalogue](../../inframeld-access-models/references/actions-and-initial-grants.md#reviewed-capability-catalogue) selects these query/policy identifiers and targets. The [fixed creator assignments](../../inframeld-access-models/references/actions-and-initial-grants.md#initial-assignments) include query inspection. Product non-query diagnostic browsing is [deferred in v1](#non-query-diagnostics). Retains exact storage/coordination/wire contracts. A query grant alone never admits inspection, and an application inspection grant cannot include policy management or explicit deletion.

For a policy change, the ordinary backend operation checks current human eligibility, project authority, expected state and operator constraints, then commits the permitted change and required audit together. Stale review or lost authority fails without silently accepting newer settings. Explicit history deletion checks its separate authority and reviewed cutoff, blocks affected reads, then performs bounded resumable cleanup. Policy management alone cannot invoke that deletion operation. Inspection is not required to delete through separately granted authority, and the review must not expose protected content.

Retention changes can affect existing history: reducing the period may make older traces expire through normal retention enforcement. Disclose that consequence in the policy review. This is not an implicit call to the separate delete-history action and does not add a second deletion grant to ordinary retention management. Increasing retention cannot restore erased content.

The human-only rule concerns caller-requested policy changes and explicit deletion. Scheduled expiry, previously admitted cleanup and source erasure continue through their owning backend workflows without a new human approval per record. It does not make unrelated source/project deletion human-only or replace those workflows' authorization. Mandatory audit, evaluation evidence and receipts retain their separate rules.

TOML import invokes the same guarded policy operation. An application may preserve the destination settings while importing otherwise authorized resources. An explicit application request to apply tracing/retention changes is denied before known-invalid plan mutations, not silently skipped or retried using a saved human login. Later authority loss after earlier steps committed produces an honest partial outcome. [Portability](../../inframeld-application-contracts/references/configuration-import-review.md#destination-review) owns plan/recovery behavior. Importing settings never imports or deletes trace history.

<a id="non-query-diagnostics"></a>

<a id="non-query-diagnostic-browsing-is-deferred-in-v1"></a>

### Non-query diagnostic browsing is deferred in v1

Product-facing browsing of generator, judge, processing and sync diagnostic traces is deferred. Host operators may inspect these diagnostics through their existing infrastructure boundary. An ordinary human login or `inspect-query-traces` grant does not acquire that authority, and there is no general Project/installation trace-read permission or product audit-browser API.

Authorized domain job status, case history and Evaluation results remain available through their own contracts. This deferral changes neither recording controls nor required security/audit, and those domain views must not become an unrestricted diagnostic trace browser. Future product browsing requires reviewed owner-specific targets/permissions and current protected-evidence checks. [ADR-0063](../../../../docs/adr/ADR-0063-defer-product-non-query-diagnostic-browsing.md) records the scope.

<a id="trace-lifecycle"></a>

<a id="keep-query-outcomes-separate-from-diagnostics"></a>

## Keep Query Outcomes Separate From Diagnostics

Alice receives a valid answer: "The cancellation period is 30 days." Saving some diagnostic spans fails. The query and its required business records succeeded, so the answer remains successful. Separately, an authorized diagnostic view reports an incomplete trace. It does not call the model again to manufacture the missing evidence. The tracing lifecycle contract accepts this behavior for both direct Pipeline queries and live Deployment queries.

<a id="a-tracing-only-failure-does-not-fail-a-healthy-query"></a>

### A tracing-only failure does not fail a healthy query

Isolate diagnostic capture, storage and exporter failures from an otherwise successful business operation. Keep queues, retained payloads, waits and delivery retries bounded. Preserve whatever permitted diagnostic evidence was confirmed saved. Distinguish confirmed complete, partial or unavailable evidence from **unknown availability** when persistence cannot be confirmed. These are outcome meanings, not a new job-state enum or a guarantee that failure metadata can always be saved during an outage.

Human warnings stay separate from the successful answer. Machine output preserves both the business outcome and permitted diagnostic availability without converting a successful query into a failed command merely because optional diagnostics are incomplete. Conversely, a successful telemetry write cannot turn a failed query into success. A command specifically requesting unavailable trace content still reports that read's actual failure/unavailability. Query success does not make every later inspection successful. Specify exact representations and existing command-result mappings.

**This is not a general fail-open rule.** Authorization, gateway destination/credential checks, budgets, required receipts, mandatory audit and other required business persistence retain their normal guarantees. If a shared database outage also prevents required accounting or authorization, follow that business failure rather than classifying the whole outage as optional tracing loss. A failure to establish capture permission must not be treated as permission to record. Suppress diagnostic capture unless policy permits it, while independently enforcing required business checks.

Only retry delivery of data that was already captured and is still permitted by the recording, destination, retention and deletion rules. A trace-delivery retry never repeats retrieval, embeddings, reranking, generation or judging.

Do not keep extra full answers in receipts, operation metadata or fallback logs to repair missing traces. Operator failure reports must exclude secrets and respect project opt-out. OpenTelemetry's [error-handling guidance](https://opentelemetry.io/docs/specs/otel/error-handling/) supports isolating telemetry failures. Inframeld additionally enforces the privacy and business-operation rules above. Neither is a promise that no trace data can be lost.

<a id="off-takes-effect-during-running-work-on-starts-with-new-work"></a>

### Off takes effect during running work. On starts with new work

Consider this illustrative sequence, with ordering established by the backend rather than the CLI clock:

| Event | Query behavior | Trace behavior |
| --- | --- | --- |
| Query A is admitted while effective recording is on | A executes normally | Capture is eligible under the relevant category/project policy. |
| Project opt-out takes effect while A is running | Do not cancel A merely because tracing was disabled | Stop further project-attributable capture and prevent buffered/queued diagnostic data from being persisted or exported after the effective boundary. |
| Recording is re-enabled before A finishes | A retains its ordinary execution contract | Do not resume A's stopped capture or replay its suppressed buffers. |
| Query B is newly admitted while effective recording is on | B executes normally | B may record under current policy. |

An execution admitted with capture off does not begin recording halfway through when policy changes to on. Already admitted queued work keeps that suppression too. Workers and retries cannot escape it by creating a new span or attempt for the same execution. Once capture is stopped for an execution/category, it remains stopped for that execution/category. A new independently admitted execution can record when eligible, but enabling tracing must not create or rerun one.

Apply this behavior to each independently controlled installation category. Project opt-out suppresses both categories for that project, while unrelated/projectless collection remains governed by its own controls. The RAG switch being off is not permission to copy RAG content into operational spans. Existing project preferences survive installation disable/re-enable and do not override operator restrictions.

The policy operation must establish the effective restriction at Inframeld's capture, persistence and delivery boundaries before reporting a confirmed "off" result. Stale workers, automatic instrumentation, buffered spans and queued retries must respect it. A lost acknowledgment is unconfirmed until original-operation recovery establishes the result. Never claim off merely because the user selected it. Apply accepted PD-PIPELINES-02 for ordering/fencing and concurrent handoff behavior, then qualify the implementation. A collector filter after sensitive capture is insufficient.

Already saved traces are not deleted by opt-out and remain subject to current access, retention and erasure. Data already handed outside Inframeld's control cannot be recalled by this switch. Do not promise withdrawal of an in-flight external delivery. No further handoff may be initiated after the effective restriction. This qualification does not enable v2 content-export connectors: v1 operational OTLP remains limited to allowed operational metadata.

<a id="content-and-ownership"></a>

## Content and Ownership

Instrument the full request/admission/worker/model path with verified correlation. Protect OpenInference workload attributes containing question, retrieved sources/order, reranker changes, final context, generation input/output and citations. Preserve exact source identity and actually retained text. Embedding vectors need not be dumped into human diagnostics.

Always exclude authentication headers, tokens, provider credentials and other secrets, including errors/debug logging. Model requests still use ModelGateway. Instrumentation creates no alternate egress path. Ragas analytics and external library exporters remain disabled while Inframeld's own tracing follows these independent controls.

The product CLI can inspect only permitted pipeline execution telemetry. Platform engineers configure operational collection. Users do not obtain full-platform API/job/admin traces through a pipeline permission. Imported evaluation evidence, execution-input snapshot metadata, diagnostic traces, accounting and content-free live receipts are distinct records with distinct purpose, not alternative routes around denied access or recording policy.

<a id="retained-logical-information"></a>

## Retained logical information

| Information | Owner and constraint |
| --- | --- |
| Operational span correlation and protected workload trace | Infrastructure and pipeline diagnostics under independent installation switches. Project opt-out suppresses all project-attributable tracing. Current inspection authority, configurable 30-day retention and erasure remain separate from mandatory audit and content-free receipts. Human/application inspection does not imply human-only policy mutation or separately authorized explicit history deletion. |

For tracing, retain separate facts about the business result, whether recording was permitted, which diagnostics are confirmed available and any separately accepted deletion request. A deletion request identifies the selected history and cutoff, together with cleanup progress. A successful query can still have partial traces or unknown trace availability.

Opt-out stops future capture and queued writes or delivery. It does not delete saved history, and re-enabling does not restart recording for a suppressed execution. Deletion instead blocks affected reads before physical cleanup completes and prevents late writers from restoring that history. It does not change future recording policy.

These facts belong to the existing operation, policy, trace and job records. They do not require a new table or job state for each phrase. Do not infer permission to keep content or an extra full-answer replay cache when tracing is off or saving fails. The tracing contract must specify schemas and enforcement under the [trace lifecycle rules](#trace-lifecycle).

Trace policy describes whether and how to record. Retained evidence describes what was saved. A deletion cutoff identifies which history must become unreadable while cleanup continues. None of these records grants inspection permission, and the cutoff does not change future recording.

Saved actor identity and audit records show who acted, not whether that person still has permission. Apply [current Access checks](#trace-authority) before disclosing content or saving guarded changes. Automatic expiry and source cleanup use their ordinary workflows. Exact fields, physical storage and wire mappings remain work for the Access and tracing contracts.
