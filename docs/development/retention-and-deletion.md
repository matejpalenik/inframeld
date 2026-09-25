# Keeping and deleting data deliberately

Use this guide when removing content, deciding how long to keep history, or explaining what a deletion completed. Assume Alice removes an old Support document while a build still uses it. Leaving it out of the next collection, blocking access to it, and erasing its bytes are three different actions.

[Access](access-control.md#documents) defines who may delete data. The [data model](data-model.md) defines which records own or reference it. [Indexing](indexing.md#retirement) handles vector retirement and physical cleanup.

**Reading route:** first distinguish ordinary removal from deletion. Then follow the deletion steps and the cases involving shared data, interrupted writes, and backups.

> **Design status:** These are accepted v1 deletion rules. Their implementation and tests are still required. Exact retention periods, some erasure policies, and the backup procedure remain decisions or qualification work as identified below.

## Contents

| Reader’s question | Start here |
| --- | --- |
| What exactly is being removed? | [1. Distinguish ownership, removal, and expiry](#scope) |
| What happens if a job finishes late? | [2. Block access before cleanup](#operation) |
| Can an old write recreate bytes? | [3. Report physical cleanup honestly](#completion) |
| Who can inspect retained or deleted records? | [4. Authorize history and completion status](#history) |
| Does a backup undo deletion? | [5. Preserve restrictions after restoration](#restoration) |
| What can a deletion result promise? | [6. Explain remaining external copies](#external) |
| Which races and limits need verification? | [7. Maintainer checks](#maintainer-checks) |
| Why these choices, and what remains open? | [8. Decision and reference map](#decision-map) |

<a id="scope"></a>

## 1. Distinguish ownership, removal, and expiry

Start by establishing exactly which person's or project's data is affected. Keep these three categories separate:

| Category | Ownership and deletion rule |
| --- | --- |
| **User identity, profile, and session records** | Handle through the account-administration flow, Kratos, and the application’s authorization rules. Removing a user is not an instruction to delete shared project data. |
| **Project-owned knowledge and releases** | Belong to the project, not automatically to the individual who uploaded or created them. Delete them only through an authorized operation for that ownership scope. |
| **Bounded operational records** | Jobs, receipts, idempotency records, audit evidence, and logs follow their defined retention and erasure rules. They are not an unlimited archive of user activity or content. |

For example, Alice can upload a manual into a shared project. Removing Alice’s account does not, by itself, delete that project’s manual or the versions other members use.

To delete a Document, a human or application needs **Delete documents** on **every group in its current, nonempty allowlist**, current project membership, and a credential that allows the operation. Add documents and Update documents do not include deletion. A group manager can explicitly grant Delete documents within that group.

Check those permissions when recording the deletion marker. Deletion covers the Document and every version of it. It does not mean removing one group's access or leaving the document out of a future collection. These accepted Access rules still need implementation and tests. [Access](access-control.md#section-bound-administration-grants-and-recovery) owns the grant rules.

A human group manager can delete a group only when no Document or active upload/source configuration refers to it. Resolve those references first, using each operation's normal permissions. Group deletion must not erase documents or silently change their access or defaults.

For an unused group, remove manager assignments before memberships, then its group-specific grants and the group itself. The [record constraints](data-model.md#group-manager-membership-constraint) explain that order. No replacement manager or permission grantor is needed for a group that will no longer exist.

Deleting an application account needs the separate, human-only **Delete application account** permission for that account. It permanently stops the account, revokes its keys, and removes its permissions, group access, and human administration grants scoped to it. It does not delete project-owned Documents or other data the application created. No replacement key administrator is needed.

Keep attribution of its earlier actions according to retention and erasure policy. Do not assign those actions to a human instead. Any retained reference to the retired identity must be unable to authenticate or reactivate it. [Access](access-control.md#section-bound-administration-grants-and-recovery) owns the permission definition.

Deleting a whole project needs the separate, human-only **Delete project** permission. The project creator receives an explicit initial grant to use and grant it. Neither general project administration nor installation administration includes it.

This permission allows erasure of **all project-owned content**, including private documents the person cannot read. It gives no right to read or share that content and does not require the ordinary delete permission for every item. Check current authority and scope when recording the project's deletion marker, then block affected access and work before cleanup. Preserve anything outside the project.

Resources deleted with the project need no replacement manager or grantor. Deleting an individual resource in a surviving project still uses its normal checks. See [Access](access-control.md#section-bound-administration-grants-and-recovery).

Deletion runs through the existing durable jobs. Save progress so an authorized deletion of project-owned or user-scoped data can continue after an interruption.

A last administrator must not leave shared resources without administration by accident. Require an authorized transfer or the explicit project/workspace deletion procedure.

The model includes an organization ownership boundary for future Enterprise Edition features. V1 does not thereby require multi-organization signup or administration. The packaging and endpoints for organization administration remain separate decisions.

### Protect required artifacts from routine expiry, not explicit erasure

**Retention** defines how long data is kept and when routine cleanup may remove it. Configuration must document defaults for sources, processing and materialization artifacts, evaluations, answer receipts, jobs, idempotency records, and logs. Exact periods are not selected here.

An **artifact** is stored content such as a source file, processing output, or manifest. A **materialization** is the prepared searchable index bound to exact source versions and processing settings. A **Deployment** selects which pipeline version serves requests.

A **pin** records that current or retained work still needs some data. It prevents routine expiry while that reference is needed.

| Situation | Required behavior |
| --- | --- |
| **Current, candidate, or designated previous Deployment target** | Pin the artifacts that target needs. Current serves requests, candidate is being tried, and the designated previous target is retained for rollback. Routine expiry must not break them. |
| **Admitted query** | Temporarily protect the selected immutable artifacts while the accepted query uses them. Admission means the application has accepted the operation for execution. |
| **Explicit source erasure or security deletion** | Invalidate affected serving state first, then follow the deletion procedure. Retention pins do not override the erasure action. Explain why an affected historical version is unavailable. |

**An immutable version is not a promise to keep its content forever.** Its recorded identity must not be silently rewritten, but explicit erasure can remove data it needs to serve.

### Keep audit and retry records useful without turning them into content archives

Normal audit operations add new events instead of rewriting earlier ones. This is **append-only** history. It does not mean personal data must be retained forever.

Keep only the actor, action, resource, time, and outcome needed as evidence, subject to the defined erasure or anonymization policy. The actor is the verified human or application that acted. Anonymization removes identifying information. The precise policy remains to be defined.

Full source text, prompts, credentials, and model responses must not enter operational logs.

An **answer receipt** records limited information about an answer, not the complete answer. An **idempotency record** recognizes a repeated request. Neither authorizes keeping sensitive responses indefinitely.

The [job and idempotency guide](jobs-and-idempotency.md) defines which safe outcome details can be retained. V1 does not durably store full production answers for retry replay.

<a id="operation"></a>

## 2. Block access before cleanup

Use the following sequence for an authorized deletion:

1. **Check who may delete what.** Authenticate the caller, check the required permission, and establish exactly which owned data the request covers.
2. **Record the deletion marker.** Commit a tombstone, a durable record that the data is deleted. Block new access and work, and invalidate affected serving references before removing bytes.
3. **Account for unfinished work.** Cancel or reconcile queued and running jobs. Every later publication must check the marker, so a late job cannot make the data available again. This cannot cancel a request already accepted by another storage service.
4. **Remove owned data.** Delete artifacts and derived data in limited-size steps that can safely repeat. Save progress. All Chroma deletion uses the [existing single vector writer](indexing.md).
5. **Handle identities and audit references.** Remove or anonymize them as required. Revoke relevant credentials and sessions through the selected identity adapter.
6. **Report what actually finished.** Mark deletion complete only after every supported step in scope succeeds. Otherwise return the defined outcome for the unfinished step.

Each step must limit how much work it does at once. Retrying it must neither expand the deletion scope nor repeat its logical effect. These properties make cleanup bounded and idempotent.

### Example: delete a project while its embedding job is running

An embedding job converts document text into numerical search vectors. Suppose project deletion starts after the job has sent a request to the model provider.

```text
Project deletion commits its tombstone
    -> New project access and work are blocked
    -> The already-sent external call may still finish
    -> The job checks publication authority and sees the tombstone
    -> Publication is rejected
    -> Owned outputs are handled by the deletion/cleanup procedure
```

Even if the model call finishes successfully, the deleted project's result cannot be published. Its cleanup goes through the existing vector writer rather than introducing a second writer that could race with it.

### Delete only known-owned data and preserve valid shared references

A **vector generation** identifies one fixed set of embedding output. Several compatible materializations can share that generation.

Before removing a shared artifact or generation, check who owns it and which retained materializations still need it. **Unknown ownership is not permission to delete. Ending one reference does not end the others.**

For example, retiring one materialization does not justify removing vectors that another retained materialization still needs. Explicit source erasure follows the different rule in [Protect required artifacts from routine expiry, not explicit erasure](retention-and-deletion.md#protect-required-artifacts-from-routine-expiry-not-explicit-erasure): invalidate the affected serving state first rather than retain that source indefinitely for rollback.

Every Chroma deletion goes through the [single vector-writer component](indexing.md), including deletion jobs. “Single” means one owner of writes, not a new service.

<a id="completion"></a>

## 3. Report physical cleanup honestly

PostgreSQL can prevent access and publication without being able to cancel a write already executing in another store. Both Chroma and SeaweedFS need explicit handling for that case.

### A delayed Chroma insert can arrive after deletion

An old immutable insert may remain unresolved after its client stops waiting. The following sequence is possible:

```text
An insert is sent; its completion remains unknown
    -> The generation is tombstoned and its records are deleted
    -> A read currently finds no records
    -> The old insert finishes and recreates an unreachable record
```

If an old write recreates a retired record, the record stays inaccessible. PostgreSQL's deletion markers and the generation filters built by the server exclude it from every query. The caller cannot supply a different authoritative filter.

**Tombstoned physical IDs are never reused.** A late insert cannot make the retired generation eligible for a new build or serving request.

A “not found” check proves only that the record was absent at that moment. An unresolved write might still recreate it. Report **“Access revoked. Physical cleanup pending.”** until earlier writes are known to have finished or become unable to finish and final cleanup is verified.

Establishing that old work can no longer arrive after cleanup is called **quiescence**. Keep unresolved-attempt evidence and allow garbage collection, the removal of unneeded data, to retry within its configured limits.

Routine retries of a candidate's saved writes do not need a Chroma restart. Finishing cleanup while an old write remains unresolved may require exceptional maintenance, operator action, or provider help. [Indexing](indexing.md) explains the distinction.

### A delayed SeaweedFS upload has the same problem

A SeaweedFS `PUT` uploads a source, artifact, or retry payload. If it is still in flight, it may finish after an earlier deletion and recreate bytes even though PostgreSQL will never publish their reference.

Give each upload attempt an immutable key that identifies its ownership scope and physical attempt. Keep evidence of uploads whose outcome is still unknown.

Mark physical deletion complete only after earlier writes have finished or cannot finish, and final cleanup has been checked. **PostgreSQL can block access and publication, but cannot cancel a request already running in the object store.**

<a id="history"></a>

## 4. Authorize history and completion status

Check current permissions every time someone reads a receipt or result, including a repeated request. Knowing an old request key or pipeline ID cannot restore revoked access.

V1 authorizes documents through group allowlists. Integrations use their application account's own configured access. A caller-supplied user ID cannot change that authority.

The access model distinguishes the verified actor from a possible **delegated subject**, a user it would be verified to represent. That leaves room for future delegation without implementing it in v1.

**Never release revoked source content or citations because a historical pipeline, receipt, or idempotency record once referred to them.** Apply current authorization at the established access-check boundary.

### Preserve a narrow way to observe deletion completion

Deleting an account or project can remove the memberships normally needed to see its jobs. The person authorized to request deletion must still have an authorized way to find out whether it finished.

A **minimal deletion-status receipt** can show the original authorized actor or an administrator the progress and remaining steps. It must not expose deleted project content.

The account-deletion and authentication flow must support that narrow status check. Former membership does not give permanent access to all historical project jobs or their contents. The exact endpoint and account flow remain implementation decisions.

Feedback follows its answer receipt's eligibility and retention period. It does not keep vectors alive. When the receipt expires, remove its rating and comment. Source or project erasure removes or redacts affected comments. Authorization must check every source in the final answer context, even evidence the answer did not cite. See the [feedback lifecycle](answer-feedback.md#lifecycle).

<a id="restoration"></a>

## 5. Preserve restrictions after restoration

The supported restore procedure must account for restrictions imposed **after** the selected backup was taken.

For example, restoring a backup from before a document was deleted must not make that document available again. Restoring an older group membership must not restore permission that was subsequently revoked.

[Recovery](upgrades-and-recovery.md) proposes an operator's off-host record of restrictive changes and deletions. Restoration invalidates old sessions and credentials and keeps access closed where the record is incomplete. This procedure still needs testing and refinement. It does not require building an automatic journal service.

Keep affected scopes closed until current restrictions and the required treatment of deleted content have been established. A restored database’s historical state is not sufficient authority to reopen access.

Document when backups expire and what that means for deletion. **A deletion request does not immediately change every immutable backup.** Report live-store cleanup separately from backup copies that remain under their retention policy.

<a id="external"></a>

## 6. Explain remaining external copies

The selected model connection determines where document content goes for external processing. Sending data outside the application environment is called **data egress**.

| Operation | Content or processing boundary to disclose |
| --- | --- |
| **Document embedding** | Chunk text goes to the selected model gateway. A chunk is a document excerpt prepared for retrieval. |
| **Answer generation** | The query and permitted source excerpts go to the selected generation connection through the gateway. |
| **Evaluation judging** | Any selected judge has its own explicitly disclosed evidence payload through the same gateway. A judge is a model that evaluates an answer. |
| **Future Chroma Cloud use** | An external-processing option for future EE, not a selected v1 requirement. |

Customer-controlled remote endpoints can have their own logging and retention. Inframeld cannot universally promise to erase those external copies merely because it deleted the local source.

A user-visible deletion result must state **which application-controlled stores were cleared, which supported steps remain unresolved, and what external or backup limits remain**.

Do not imply that Inframeld can delete history from every provider. Add a provider-specific integration only when the selected provider offers a relevant supported mechanism.

A deletion endpoint implements these technical boundaries. **It does not, by itself, establish privacy or legal compliance**, which is broader than this architecture.

<a id="maintainer-checks"></a>

## 7. Maintainer checks

These are acceptance requirements, not evidence that the implementation has passed them.

| Area | Required verification |
| --- | --- |
| **Ownership and scope** | Deny cross-scope deletion. Removing a user must not silently delete project-owned knowledge, and the last administrator must not orphan shared ownership. |
| **Access-group dependencies** | Reject group deletion while any Document or active upload/source configuration refers to it, including concurrent admissions/configuration changes. Authorized deletion of an unused group removes its manager assignments before memberships and its own grants, requires no replacement manager, and never changes document policies or defaults. |
| **Tombstone ordering** | Commit the tombstone and block affected access/work before cleanup. A late job must fail its publication check. |
| **Shared vectors** | Preserve vectors still needed by another retained materialization. Route every Chroma deletion through the designated mutation owner. |
| **Crash recovery** | Interrupt deletion and resume its bounded, idempotent steps without expanding scope or losing unresolved-step visibility. |
| **Late external writes** | Exercise delayed Chroma inserts and SeaweedFS uploads after deletion. Keep them inaccessible and report physical cleanup as pending until completion/quiescence and final cleanup are established. |
| **Current authorization** | Deny revoked receipt/result access and idempotency replay. Verify group allowlists, fixed integration authority, and scoped opaque credentials rather than trusting caller-supplied identities. |
| **Content minimization** | Keep secrets and full production answers out of replay caches, and source text, prompts, credentials, and model responses out of operational logs. |
| **Feedback** | Check uncited final-context sources, expire feedback with its receipt, and remove/redact affected comments on erasure without creating a permanent archive. |
| **Account and storage procedures** | Validate the selected Kratos and SeaweedFS procedures, including an authorized way to observe deletion completion without reopening deleted content. |
| **Backup restore** | Restore a backup that predates a deletion tombstone and verify that current restrictions and deleted-content exclusion remain enforced. |

The checks above express accepted requirements. Backup timing proposals, future organization packaging, and finer access-control lists are separate work.

<a id="decision-map"></a>

## 8. Decision and reference map

Exact retention periods, erasure/anonymization policy, and the narrow deletion-status endpoint still need implementation decisions. [Recovery](upgrades-and-recovery.md#restrictions) owns the provisional off-host restriction register. Explicit erasure can make an old release unavailable. Keeping its history does not require retaining its content forever or guarantee deletion from every provider and backup.

| Decision | Rationale |
| --- | --- |
| [ADR-0039](../adr/ADR-0039-block-access-before-resumable-physical-deletion.md) | Block access before resumable physical deletion. |
