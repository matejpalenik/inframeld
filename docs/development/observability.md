# Operational Tracing and Protected Pipeline Diagnostics

Alice asks why her R.U.R. answer is wrong. She needs to see which passages were retrieved, how reranking changed their order, what the generation model received and what it answered. She does not need access to the installation's entire operational trace store.

An operator has a different need: following requests through background jobs and diagnosing service failures. Both use OpenTelemetry to record tracing data and OTLP to transport it. Model and RAG traces use the OpenInference attribute conventions so their contents have a standard meaning.

This is accepted architecture, not implemented instrumentation or a qualified exporter. [The delivery plan](cli-delivery-plan.md) names contract and runtime prerequisites. Phoenix/LangSmith connectors are deferred; standards alignment is preparation for interoperability, not proof that every external product accepts every attribute.

## Contents

| Reader's question | Start here |
| --- | --- |
| Which switches control capture? | [Recording controls](#recording-controls) |
| Who may inspect or change it? | [Authority](#trace-authority) |
| What if tracing fails or is switched off during a query? | [Failure and transition contract](#trace-lifecycle) |
| What can be recorded? | [Content and ownership](#content-and-ownership) |
| What happens to existing history? | [Retention and deletion](#retention-and-failure) |

## Recording Controls

| Control | Meaning |
| --- | --- |
| Installation operational tracing switch | Enables/disables platform operational spans independently of RAG workload capture |
| Installation workload tracing switch | Can disable RAG workload capture completely; users cannot override this |
| Installation workload default/lock policy | Establishes new-project default and whether projects may change it; an operator may default to no recording |
| Project workload preference | Opts out of all future project-attributable tracing, including its operational spans, or re-enables eligible recording within installation policy; new projects otherwise opt in |
| Inspection authority | Determines who may read already recorded protected workload evidence; never determines whether the initiating workload records |

**The caller's inspection permission must not determine whether recording happens.** A customer application can produce a trace it cannot inspect, while an authorized engineer can later inspect it. Conversely, no permission can recover content that was never recorded, expired or erased. Recording defaults/locks and inspection grants are different concepts.

Mandatory security/audit records are not optional diagnostic tracing. Neither switch disables required authorization/audit behavior. The workload switch must suppress workload evidence even when operational tracing is enabled; operational spans must not become a hidden copy of forbidden prompts or answers.

When a project opts out, stop its operational traces as well as its RAG traces. This does not turn off tracing for unrelated projects or health checks that belong to no project. Keep the project's saved preference even while an installation policy prevents recording.

[The trace lifecycle](#trace-lifecycle) explains what happens to queued and running work. The [tracing contract](https://github.com/matejpalenik/inframeld/issues/147) still needs the exact coordination, storage and wire mechanisms.

<a id="trace-authority"></a>

## Who May Inspect or Change Tracing

SupportBot can help Alice diagnose an answer when it has explicit trace-inspection permission and current access to the captured sources. That does not let it switch recording off or erase the history it is inspecting. The [project tracing ticket](https://github.com/matejpalenik/inframeld/issues/149) settles this eligibility boundary; [Access](access-control.md#trace-authority) owns grants and enforcement.

| Requested action | Eligible caller and required authority |
| --- | --- |
| Inspect permitted pipeline traces | Active humans or application accounts with explicit current inspection authority and current source access |
| Enable or disable project tracing | Active humans with current project trace-policy authority |
| Change project trace retention | Active humans with current project trace-policy authority, within operator limits |
| Explicitly delete past project traces | Active humans with separate current project trace-deletion authority |

There is no all-powerful tracing role. Query permission, project membership or knowing a trace ID does not grant inspection. Being human does not by itself permit a policy change or deletion.

Live-query inspection names an exact Deployment. Direct-query inspection names an exact Pipeline. Neither permission grants the other, and neither introduces an Experiment resource or permission. Either can reveal other callers' questions and answers on that resource. Explain that when granting access.

Check access to every captured source, including retrieved candidates excluded from the final context. The [Access](https://github.com/matejpalenik/inframeld/issues/116) and [tracing](https://github.com/matejpalenik/inframeld/issues/147) contracts still need concrete permission mappings, initial grant rules and capabilities for non-query work.

For a policy change, the ordinary backend operation checks current human eligibility, project authority, expected state and operator constraints, then commits the permitted change and required audit together. Stale review or lost authority fails without silently accepting newer settings. Explicit history deletion checks its separate authority and reviewed cutoff, blocks affected reads, then performs bounded resumable cleanup. Policy management alone cannot invoke that deletion operation; inspection is not required to delete through separately granted authority, and the review must not expose protected content.

Retention changes can affect existing history: reducing the period may make older traces expire through normal retention enforcement. Disclose that consequence in the policy review. This is not an implicit call to the separate delete-history action and does not add a second deletion grant to ordinary retention management. Increasing retention cannot restore erased content.

The human-only rule concerns caller-requested policy changes and explicit deletion. Scheduled expiry, previously admitted cleanup and source erasure continue through their owning backend workflows without a new human approval per record. It does not make unrelated source/project deletion human-only or replace those workflows' authorization. Mandatory audit, evaluation evidence and receipts retain their separate rules.

TOML import invokes the same guarded policy operation. An application may preserve the destination settings while importing otherwise authorized resources. An explicit application request to apply tracing/retention changes is denied before known-invalid plan mutations, not silently skipped or retried using a saved human login. Later authority loss after earlier steps committed produces an honest partial outcome. [Portability](configuration-portability.md#destination-review) owns plan/recovery behavior; importing settings never imports or deletes trace history.

<a id="trace-lifecycle"></a>

## Keep Query Outcomes Separate From Diagnostics

Alice receives a valid answer: "The cancellation period is 30 days." Saving some diagnostic spans fails. The query and its required business records succeeded, so the answer remains successful. Separately, an authorized diagnostic view reports an incomplete trace. It does not call the model again to manufacture the missing evidence. The [tracing lifecycle contract](https://github.com/matejpalenik/inframeld/issues/149) accepts this behavior for both direct Pipeline queries and live Deployment queries.

### A tracing-only failure does not fail a healthy query

Isolate diagnostic capture, storage and exporter failures from an otherwise successful business operation. Keep queues, retained payloads, waits and delivery retries bounded. Preserve whatever permitted diagnostic evidence was confirmed saved. Distinguish confirmed complete, partial or unavailable evidence from **unknown availability** when persistence cannot be confirmed. These are outcome meanings, not a new job-state enum or a guarantee that failure metadata can always be saved during an outage.

Human warnings stay separate from the successful answer. Machine output preserves both the business outcome and permitted diagnostic availability without converting a successful query into a failed command merely because optional diagnostics are incomplete. Conversely, a successful telemetry write cannot turn a failed query into success. A command specifically requesting unavailable trace content still reports that read's actual failure/unavailability; query success does not make every later inspection successful. #147/#156 specify exact representations and existing command-result mappings.

**This is not a general fail-open rule.** Authorization, gateway destination/credential checks, budgets, required receipts, mandatory audit and other required business persistence retain their normal guarantees. If a shared database outage also prevents required accounting or authorization, follow that business failure rather than classifying the whole outage as optional tracing loss. A failure to establish capture permission must not be treated as permission to record; suppress diagnostic capture unless policy permits it, while independently enforcing required business checks.

Only retry delivery of data that was already captured and is still permitted by the recording, destination, retention and deletion rules. A trace-delivery retry never repeats retrieval, embeddings, reranking, generation or judging.

Do not keep extra full answers in receipts, operation metadata or fallback logs to repair missing traces. Operator failure reports must exclude secrets and respect project opt-out. OpenTelemetry's [error-handling guidance](https://opentelemetry.io/docs/specs/otel/error-handling/) supports isolating telemetry failures. Inframeld additionally enforces the privacy and business-operation rules above. Neither is a promise that no trace data can be lost.

### Off takes effect during running work; on starts with new work

Consider this illustrative sequence, with ordering established by the backend rather than the CLI clock:

| Event | Query behavior | Trace behavior |
| --- | --- | --- |
| Query A is admitted while effective recording is on | A executes normally | Capture is eligible under the relevant category/project policy. |
| Project opt-out takes effect while A is running | Do not cancel A merely because tracing was disabled | Stop further project-attributable capture and prevent buffered/queued diagnostic data from being persisted or exported after the effective boundary. |
| Recording is re-enabled before A finishes | A retains its ordinary execution contract | Do not resume A's stopped capture or replay its suppressed buffers. |
| Query B is newly admitted while effective recording is on | B executes normally | B may record under current policy. |

An execution admitted with capture off does not begin recording halfway through when policy changes to on. Already admitted queued work keeps that suppression too. Workers and retries cannot escape it by creating a new span or attempt for the same execution. Once capture is stopped for an execution/category, it remains stopped for that execution/category. A new independently admitted execution can record when eligible, but enabling tracing must not create or rerun one.

Apply this behavior to each independently controlled installation category. Project opt-out suppresses both categories for that project, while unrelated/projectless collection remains governed by its own controls. The RAG switch being off is not permission to copy RAG content into operational spans. Existing project preferences survive installation disable/re-enable and do not override operator restrictions.

The policy operation must establish the effective restriction at Inframeld's capture, persistence and delivery boundaries before reporting a confirmed "off" result. Stale workers, automatic instrumentation, buffered spans and queued retries must respect it. A lost acknowledgment is unconfirmed until original-operation recovery establishes the result; never claim off merely because the user selected it. #147 must specify and qualify the exact ordering/fencing and concurrent handoff behavior, without relying solely on a collector filter after sensitive capture.

Already saved traces are not deleted by opt-out and remain subject to current access, retention and erasure. Data already handed outside Inframeld's control cannot be recalled by this switch; do not promise withdrawal of an in-flight external delivery. No further handoff may be initiated after the effective restriction. This qualification does not enable v2 content-export connectors: v1 operational OTLP remains limited to allowed operational metadata.

### Deletion blocks reads before physical cleanup completes

Turning capture off and explicitly deleting past history are different operations. A separately authorized human reviews a bounded deletion selection/cutoff. Once the backend admits that deletion and blocks affected reads, report unreadable history separately from in-progress physical cleanup. Before that confirmed boundary, do not claim the data is already unreadable. The deletion does not change future recording policy or erase unrelated records such as explicitly admitted evaluation evidence.

Late completion, buffered writes and retries must not recreate history covered by the deletion selection/cutoff. If cleanup is interrupted, restrictions remain effective and existing durable cleanup resumes under its original operation identity. Do not admit a broader, newer deletion merely because an acknowledgment was lost. Increasing retention or turning recording on cannot restore erased history. [Retention and deletion](retention-and-deletion.md#trace-history-deletion) owns the cleanup distinction and external-copy limits.

## Content and Ownership

Instrument the full request/admission/worker/model path with verified correlation. Protect OpenInference workload attributes containing question, retrieved sources/order, reranker changes, final context, generation input/output and citations. Preserve exact source identity and actually retained text. Embedding vectors need not be dumped into human diagnostics.

Always exclude authentication headers, tokens, provider credentials and other secrets, including errors/debug logging. Model requests still use ModelGateway; instrumentation creates no alternate egress path. Ragas analytics and external library exporters remain disabled while Inframeld's own tracing follows these independent controls.

The product CLI can inspect only permitted pipeline execution telemetry. Platform engineers configure operational collection; users do not obtain full-platform API/job/admin traces through a pipeline permission. Imported evaluation evidence, execution-input snapshot metadata, diagnostic traces, accounting and content-free live receipts are distinct records with distinct purpose, not alternative routes around denied access or recording policy.

## Retention and Failure

Default workload trace retention is 30 days and deployment-configurable. Explicit deletion by a separately authorized human is independent of disabling future capture. Expired or deletion-blocked content is unreadable even while physical cleanup is pending. Late writers/retries must not recreate history covered by the deletion cutoff. Apply current inspection and source access on reads; source erasure removes protected derived content through ordinary durable cleanup. Report unavailable/partial cleanup honestly rather than promise permanent reproducibility.

Bound span/event size, retained content, query windows, exporter queues and resource use. Exact storage/exporter topology, capability names, API schemas and numerical bounds require specification. Test real network/log behavior with both switches, opt-out/re-enable, revoked inspection/source access, erasure, exporter failure and cancellation. A documentation link to a standard is not a passed test.

| Tracing qualification scenario | Required observation |
| --- | --- |
| Diagnostic storage/exporter fails but business checks and required records succeed | Preserve query success, confirmed partial evidence and honest diagnostic availability. Do not repeat model calls. |
| The same fault also prevents required accounting/audit/receipt persistence | Apply the owning business failure contract, not tracing-only success. |
| Off occurs between capture and persistence/export, then on before the query finishes | Suppress remaining capture and queued writes/delivery, keep that execution suppressed, and permit only newly admitted eligible executions to record. |
| Policy or storage acknowledgment is lost | Report unknown/unconfirmed state until safe read/recovery, never fabricated off, saved, lost or complete. |
| Deletion is admitted, cleanup stops, and a writer finishes late | Reads remain blocked, late writes cannot restore deleted history, and original bounded cleanup can resume without changing future capture. |
| Human and JSON clients inspect partial or protected results | Preserve the same permitted outcome meanings, safe source/inspection checks, no hidden reconstruction and no paid rerun. |

### Implementation and qualification

| Responsibility | Owning work |
| --- | --- |
| Exact permissions and transition contracts | [Access contracts](https://github.com/matejpalenik/inframeld/issues/116) and [tracing contracts](https://github.com/matejpalenik/inframeld/issues/147) |
| Operational instrumentation | [Platform tracing](https://github.com/matejpalenik/inframeld/issues/148) |
| Capture, inspection, policy changes and deletion | [Project tracing](https://github.com/matejpalenik/inframeld/issues/149) |
| CLI query outcomes and trace controls | [Query presentation](https://github.com/matejpalenik/inframeld/issues/173) and [trace presentation](https://github.com/matejpalenik/inframeld/issues/177) |
| Import through the same policy operations | [Portability contract](https://github.com/matejpalenik/inframeld/issues/151), [backend import](https://github.com/matejpalenik/inframeld/issues/154) and [CLI import](https://github.com/matejpalenik/inframeld/issues/184) |
| Runtime evidence | [Tracing qualification](https://github.com/matejpalenik/inframeld/issues/150), [portability qualification](https://github.com/matejpalenik/inframeld/issues/155) and [CLI qualification](https://github.com/matejpalenik/inframeld/issues/187) |

Test permitted application inspection and denied application policy changes, denied unauthorized humans, separate deletion permission and access revoked before disclosure or commit. Also cover automatic expiry, source cleanup and imports that preserve or explicitly apply policies.

These are requirements for future tests, not evidence that product tests ran. This guide selects no new trace engine, physical table, permission identifier, endpoint or external connector.
