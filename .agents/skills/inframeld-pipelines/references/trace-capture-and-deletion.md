# Stop trace capture and delete selected history

Alice turns tracing off while an answer is running, then turns it on again. That execution stays suppressed. Deleting saved history is a separate operation that blocks affected reads before physical cleanup completes.

<a id="recording-controls"></a>

## Apply accepted PD-PIPELINES-02

Accepted [PD-PIPELINES-02](decision-trace-policy-fencing.md#approved-resolution) selects this workflow's detailed contract. Tracing should help diagnose a query without becoming a second, uncontrolled copy of private data. A confirmed off action must affect running processes and queued writes, not just a settings screen. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## Recording Controls

| Control | Meaning |
| --- | --- |
| Installation operational tracing switch | Enables/disables platform operational spans independently of RAG workload capture |
| Installation workload tracing switch | Can disable RAG workload capture completely. Users cannot override this |
| Installation workload default/lock policy | Establishes new-project default and whether projects may change it. An operator may default to no recording |
| Project workload preference | Opts out of all future project-attributable tracing, including its operational spans, or re-enables eligible recording within installation policy. New projects otherwise opt in |
| Inspection authority | Determines who may read already recorded protected workload evidence. Never determines whether the initiating workload records |

**The caller's inspection permission must not determine whether recording happens.** A customer application can produce a trace it cannot inspect, while an authorized engineer can later inspect it. Conversely, no permission can recover content that was never recorded, expired or erased. Recording defaults/locks and inspection grants are different concepts.

Mandatory security/audit records are not optional diagnostic tracing. Neither switch disables required authorization/audit behavior. The workload switch must suppress workload evidence even when operational tracing is enabled. Operational spans must not become a hidden copy of forbidden prompts or answers.

When a project opts out, stop its operational traces as well as its RAG traces. This does not turn off tracing for unrelated projects or health checks that belong to no project. Keep the project's saved preference even while an installation policy prevents recording.

[The trace lifecycle](query-tracing-and-privacy.md#trace-lifecycle) explains what happens to queued and running work. Accepted PD-PIPELINES-02 selects the epoch, sticky suppression, acknowledgment barrier and deletion fencing. Native storage/wire delivery remains implementation work.

<a id="deletion-blocks-reads-before-physical-cleanup-completes"></a>

### Deletion blocks reads before physical cleanup completes

Turning capture off and explicitly deleting past history are different operations. A separately authorized human reviews a bounded deletion selection/cutoff. Once the backend admits that deletion and blocks affected reads, report unreadable history separately from in-progress physical cleanup. Before that confirmed boundary, do not claim the data is already unreadable. The deletion does not change future recording policy or erase unrelated records such as explicitly admitted evaluation evidence.

Late completion, buffered writes and retries must not recreate history covered by the deletion selection/cutoff. If cleanup is interrupted, restrictions remain effective and existing durable cleanup resumes under its original operation identity. Do not admit a broader, newer deletion merely because an acknowledgment was lost. Increasing retention or turning recording on cannot restore erased history. [Retention and deletion](#trace-history-deletion) owns the cleanup distinction and external-copy limits.

<a id="retention-and-failure"></a>

## Retention and Failure

Default workload trace retention is 30 days and deployment-configurable. Explicit deletion by a separately authorized human is independent of disabling future capture. Expired or deletion-blocked content is unreadable even while physical cleanup is pending. Late writers/retries must not recreate history covered by the deletion cutoff. Apply current inspection and source access on reads. Source erasure removes protected derived content through ordinary durable cleanup. Report unavailable/partial cleanup honestly rather than promise permanent reproducibility.

Bound span/event size, retained content, query windows, exporter queues and resource use. Exact storage/exporter topology, capability names, API schemas and numerical bounds require specification. Test real network/log behavior with both switches, opt-out/re-enable, revoked inspection/source access, erasure, exporter failure and cancellation. A documentation link to a standard is not a passed test.

| Tracing qualification scenario | Required observation |
| --- | --- |
| Diagnostic storage/exporter fails but business checks and required records succeed | Preserve query success, confirmed partial evidence and honest diagnostic availability. Do not repeat model calls. |
| The same fault also prevents required accounting/audit/receipt persistence | Apply the owning business failure contract, not tracing-only success. |
| Off occurs between capture and persistence/export, then on before the query finishes | Suppress remaining capture and queued writes/delivery, keep that execution suppressed, and permit only newly admitted eligible executions to record. |
| Policy or storage acknowledgment is lost | Report unknown/unconfirmed state until safe read/recovery, never fabricated off, saved, lost or complete. |
| Deletion is admitted, cleanup stops, and a writer finishes late | Reads remain blocked, late writes cannot restore deleted history, and original bounded cleanup can resume without changing future capture. |
| Human and JSON clients inspect partial or protected results | Preserve the same permitted outcome meanings, safe source/inspection checks, no hidden reconstruction and no paid rerun. |

<a id="implementation-and-qualification"></a>

### Implementation and qualification

Test permitted application inspection and denied application policy changes, denied unauthorized humans, separate deletion permission and access revoked before disclosure or commit. Also cover automatic expiry, source cleanup and imports that preserve or explicitly apply policies.

These are requirements for future tests, not evidence that product tests ran. This guide selects no new trace engine, physical table, permission identifier, endpoint or external connector.

<a id="cli-era-content-and-reset-boundaries"></a>

<a id="trace-history-imported-evidence-and-local-reset"></a>

### Trace history, imported evidence and local reset

[Observability](query-tracing-and-privacy.md) distinguishes operational telemetry, protected workload traces, mandatory audit and content-free receipts. Workload traces default to 30-day configurable retention. Project opt-out stops all future project-attributable tracing, including operational spans for that project. Unrelated/projectless operation and mandatory audit remain separate. Explicit past-trace deletion is separate and may need durable cleanup. Neither trace history nor evaluation storage is an access/erasure bypass.

Under project tracing controls, only an active, explicitly authorized human may change project tracing/retention. Explicit past-trace deletion requires a separate human grant to delete traces for that project. This is not authority to delete the project itself. Authorized humans/applications may inspect permitted pipeline traces with current source access. Inspection does not grant policy management or deletion, and policy management does not grant the explicit deletion action.

For example, Alice reduces retention and some old traces become expired. Warn about this consequence during review, but do not require a second deletion permission for ordinary retention management. Explicitly deleting existing history is a different operation. It requires its own deletion permission and a reviewed cutoff identifying the history to delete.

Expired history and history blocked by deletion must be unreadable before physical cleanup finishes. Retries and late writers must not restore it. Automatic expiry, previously accepted cleanup and source erasure require no fresh human approval per record. This does not change who may perform unrelated source or project deletion.

[Trace authority](query-tracing-and-privacy.md#trace-authority) and the [trace lifecycle](query-tracing-and-privacy.md#trace-lifecycle) own these rules. Accepted PD-PIPELINES-02 selects enforcement policy. Its implementation and assembled qualification remain required.

<a id="trace-history-deletion"></a>

<a id="trace-opt-out-is-not-deletion"></a>

#### Trace opt-out is not deletion

Alice turns tracing off while a query is running. Once the restriction takes effect, stop further capture for that project and prevent queued diagnostic data from being saved or delivered. The query may still finish if it remains permitted.

Already saved history keeps its ordinary access and retention rules. Re-enabling tracing applies to newly accepted eligible executions. It does not restart capture for the running query or release its suppressed buffers. [Observability](query-tracing-and-privacy.md#trace-lifecycle) owns these recording rules. Turning recording off is not erasure.

If Alice separately has explicit trace-deletion authority, she may admit deletion of a reviewed history selection/cutoff. Block affected reads at that confirmed boundary, then perform bounded physical cleanup through the existing durable operation. While cleanup is pending or interrupted, affected content stays unreadable and late writers/retries cannot recreate it. Report "cleanup in progress" rather than "all bytes deleted" until completion is verified. Recover a lost acknowledgment using the original operation and cutoff, not a fresh broader deletion. Future recording policy remains unchanged.

Retention increases and re-enabling cannot recover erased content. Mandatory audit, required receipts/accounting and separately admitted evaluation evidence retain their own lifecycles. Explicit trace deletion is not authority to erase those stores. Nor may they become a hidden copy of missing diagnostics. Data already delivered outside Inframeld's control cannot be recalled merely by local opt-out/deletion. Preserve the [external-copy limitations](../../inframeld-knowledge/references/deletion-and-retention.md#external).

Imported evaluation questions, references and excerpts are protected even before source linking. Their explicit destination audience survives linking/reimport/edits. Linked evidence additionally requires current source access. Retention and authorized erasure cover unresolved imported content too. Portable files already downloaded to another installation cannot be recalled. Export permissions must account for that limitation.

CLI factory reset removes the owned managed-local installation's data and the current OS user's CLI state, including local copies of remote target definitions/logins. It does not delete original source files, remote installations or unrelated/shared resources. Reset is not project deletion, backup/restore or merely stopping services. Partial cleanup must remain visible. The [V1 scope](../../inframeld-architecture/references/v1-scope-and-extension-boundaries.md) tracks these distinct implementations and qualification.
