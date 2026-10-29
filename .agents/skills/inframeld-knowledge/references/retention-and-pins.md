# Expire retained data without confusing erasure

Alice retains P1 for rollback while newer knowledge is prepared. A pin records that ordinary cleanup must keep a dependency. It does not defeat explicit source erasure or guarantee that history stays readable forever.

<a id="distinguish-ownership-removal-and-expiry"></a>

<a id="scope"></a>

<a id="1-distinguish-ownership-removal-and-expiry"></a>

## Apply accepted PD-KNOWLEDGE-02

Accepted [PD-KNOWLEDGE-02](decision-retention-erasure-policy.md#approved-resolution) selects this workflow's detailed contract. Keeping everything forever eventually exhausts the host and makes erasure harder. Finite defaults make normal growth predictable, while safety obligations cannot be discarded just because a timer expired. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## Distinguish ownership, removal, and expiry

Start by establishing exactly which person's or project's data is affected. Keep these three categories separate:

| Category | Ownership and deletion rule |
| --- | --- |
| **User identity, profile, and session records** | Handle through the account-administration flow, Kratos, and the application’s authorization rules. Removing a user is not an instruction to delete shared project data. |
| **Project-owned knowledge and releases** | Belong to the project, not automatically to the individual who uploaded or created them. Delete them only through an authorized operation for that ownership scope. |
| **Bounded operational records** | Jobs, receipts, idempotency records, audit evidence, and logs follow their defined retention and erasure rules. They are not an unlimited archive of user activity or content. |

For example, Alice can upload a manual into a shared project. Removing Alice’s account does not, by itself, delete that project’s manual or the versions other members use.

To delete a Document, a human or application needs **Delete documents** on **every group in its current, nonempty allowlist**, current project membership, and a credential that allows the operation. Add documents and Update documents do not include deletion. A group manager can explicitly grant Delete documents within that group.

Check those permissions when recording the deletion marker. Deletion covers the Document and every version of it. It does not mean removing one group's access or leaving the document out of a future collection. These accepted Access rules still need implementation and tests. [Access](../../inframeld-access-models/references/memberships-groups-and-handover.md#section-bound-administration-grants-and-recovery) owns the grant rules.

A human group manager can delete a group only when no Document or active upload/source configuration refers to it. Resolve those references first, using each operation's normal permissions. Group deletion must not erase documents or silently change their access or defaults.

For an unused group, remove manager assignments before memberships, then its group-specific grants and the group itself. The [record constraints](../../inframeld-access-models/references/access-lifecycle-persistence.md#group-manager-membership-constraint) explain that order. No replacement manager or permission grantor is needed for a group that will no longer exist.

Deleting an application account needs the separate, human-only **Delete application account** permission for that account. It permanently stops the account, revokes its keys, and removes its permissions, group access, and human administration grants scoped to it. It does not delete project-owned Documents or other data the application created. No replacement key administrator is needed.

Keep attribution of its earlier actions according to retention and erasure policy. Do not assign those actions to a human instead. Any retained reference to the retired identity must be unable to authenticate or reactivate it. [Access](../../inframeld-access-models/references/memberships-groups-and-handover.md#section-bound-administration-grants-and-recovery) owns the permission definition.

Deleting a whole project needs the separate, human-only **Delete project** permission. The project creator receives an explicit initial grant to use and grant it. Neither general project administration nor installation administration includes it.

This permission allows erasure of **all project-owned content**, including private documents the person cannot read. It gives no right to read or share that content and does not require the ordinary delete permission for every item. Check current authority and scope when recording the project's deletion marker, then block affected access and work before cleanup. Preserve anything outside the project.

Resources deleted with the project need no replacement manager or grantor. Deleting an individual resource in a surviving project still uses its normal checks. See [Access](../../inframeld-access-models/references/memberships-groups-and-handover.md#section-bound-administration-grants-and-recovery).

Deletion runs through the existing durable jobs. Save progress so an authorized deletion of project-owned or user-scoped data can continue after an interruption.

A last administrator must not leave shared resources without administration by accident. Require an authorized transfer or the explicit project/workspace deletion procedure.

The model includes an organization ownership boundary for future Enterprise Edition features. V1 does not thereby require multi-organization signup or administration. The packaging and endpoints for organization administration remain separate decisions.

<a id="protect-required-artifacts-from-routine-expiry-not-explicit-erasure"></a>

### Protect required artifacts from routine expiry, not explicit erasure

**Retention** defines how long data is kept and when routine cleanup may remove it. Configuration must document defaults for sources, processing and materialization artifacts, evaluations, answer receipts, jobs, idempotency records, and logs. Exact periods are not selected here.

Generated evaluation questions and reference answers can disclose their source even when no excerpt is displayed. Track their source provenance and apply current access and erasure to drafts, accepted revisions, expected passages, answers, and claim judgments. Removing a case from future benchmarks is not the same operation as erasing this protected content. An immutable benchmark preserves identity and history, not permission to retain erased text.

Evaluation evidence and diagnostic traces are distinct stores. A project trace opt-out does not erase an explicitly admitted evaluation, and an evaluation must not recreate an otherwise disabled trace stream. Disclose saved evaluation content at admission and do not silently give it the diagnostic trace retention period. On source erasure, block derived-content reads and new model sends before resumable cleanup. Retain only permitted non-content unavailability markers. [Evaluation](../../inframeld-evaluation/references/history-and-dataset-transfer.md#history) owns review/history behavior.

Working configuration revisions and execution-input snapshots also have their own bounded lifecycle. Restoring configuration creates a new current revision. It does not restore erased source bytes, expired materializations or revoked credentials. A retained snapshot records what ran but does not keep every historical index alive forever. Active direct-query/preparation/evaluation operations use bounded pins, while routine cleanup preserves artifacts still referenced by a live release. Deleting a query-history reference must not delete shared vectors needed elsewhere.

Direct-query answers and context may be captured only through the separately authorized, policy-controlled result/diagnostic behavior. Do not use snapshot provenance or idempotency storage as an undeclared full-answer archive when tracing is disabled. Explicit evaluation evidence remains governed by the paragraph above. Current access applies to configuration history, snapshot metadata, excerpts, list previews and exports. Missing historical dependencies produce an unavailable result, not silent re-embedding or reconstruction from a different corpus. Accepted PD-KNOWLEDGE-02 selects snapshot/history retention and storage bounds. This decision introduces no unlimited retention default.

An **artifact** is stored content such as a source file, processing output, or manifest. A **materialization** is the prepared searchable index bound to exact source versions and processing settings. A **Deployment** selects which pipeline version serves requests.

A **pin** records that current or retained work still needs some data. It prevents routine expiry while that reference is needed.

| Situation | Required behavior |
| --- | --- |
| **Current, candidate, or designated previous Deployment target** | Pin the artifacts that target needs. Current serves requests, candidate is being tried, and the designated previous target is retained for rollback. Routine expiry must not break them. |
| **Admitted query** | Temporarily protect the selected immutable artifacts while the accepted query uses them. Admission means the application has accepted the operation for execution. |
| **Explicit source erasure or security deletion** | Invalidate affected serving state first, then follow the deletion procedure. Retention pins do not override the erasure action. Explain why an affected historical version is unavailable. |

**An immutable version is not a promise to keep its content forever.** Its recorded identity must not be silently rewritten, but explicit erasure can remove data it needs to serve.

<a id="keep-audit-and-retry-records-useful-without-turning-them-into-content-archives"></a>

### Keep audit and retry records useful without turning them into content archives

Connection access revisions are non-secret administrative history under [ADR-0054](../../../../docs/adr/ADR-0054-use-shared-current-model-connections.md), not selectable historical runtime configurations or a permanent archive. Preserve only the permitted metadata needed to explain retained executions and current references under ordinary retention/access rules. Credential bytes never enter access-history, Pipeline, evaluation or receipt records. Restoration proposes settings and does not restore old secrets.

An existing connection's prepared or in-progress embedding dependencies include retained rollback data, not only live pointers. Ordinary retirement/deletion remains reference-aware and cannot be invoked implicitly to make a blocked update pass. History inspection, tracing opt-out and erasure remain separate: minimal execution attribution cannot recreate prohibited diagnostic payloads or authorize old endpoints. Missing retained settings make a historical restore proposal unavailable. They do not justify guessing them.

Normal audit operations add new events instead of rewriting earlier ones. This is **append-only** history. It does not mean personal data must be retained forever.

Keep only the actor, action, resource, time, and outcome needed as evidence, subject to the defined erasure or anonymization policy. The actor is the verified human or application that acted. Anonymization removes identifying information. Accepted [PD-KNOWLEDGE-02](decision-retention-erasure-policy.md#approved-resolution) selects finite ordinary audit retention and minimal non-content/non-reusable attribution while removing unnecessary direct personal attributes. Safety obligations and backup restriction evidence retain their required exception. Native storage representations and erasure qualification remain implementation work.

Full source text, prompts, credentials, and model responses must not enter operational logs.

An **answer receipt** records limited information about an answer, not the complete answer. An **idempotency record** recognizes a repeated request. Neither authorizes keeping sensitive responses indefinitely.

The [job and idempotency guide](../../inframeld-application-contracts/references/jobs-and-recovery.md) defines which safe outcome details can be retained. V1 does not durably store full production answers for retry replay.
