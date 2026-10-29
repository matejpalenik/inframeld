# Block a Project and finish its original deletion

Alice deletes Support while its cleanup still has work to do. She might not be allowed to read every HR document inside it. Delete project authorizes this exact scoped destruction, not reading or sharing its contents.

## Authority and ownership

Delete project is a separate human-only Project permission, initially assigned to the creator through ordinary removable grants. It covers all Project-owned contents. Alice does not need every resource's Delete permission or management of every document group.

Access admits the change under current eligibility, membership, exact Delete project authority and reviewed state. Application lifecycle stops the Project's applications and revokes their keys. Knowledge and the other owners perform resumable removal of their own data. No worker may widen the admitted Project scope.

Deleting one resource in a live Project follows that resource's narrower rules. Removing a human or an application does not silently erase Project-owned work. Resources being erased need no replacement manager or grantor, while ordinary departure from surviving shared resources still requires its handover safeguards.

<a id="project-deletion"></a> <a id="a-project-is-retired-while-it-contains-private-data"></a> <a id="continue-only-the-project-deletion-that-was-admitted"></a>

## Follow one admitted deletion

1. Authenticate Alice and check current human eligibility, Project membership, exact Delete project and reviewed revision under the shared Organization/Project coordination.
2. Commit the authoritative Project block, audit, original operation binding and exact durable cleanup obligation together. A denial or stale review leaves no partial block.
3. Fence affected reads and new work. Racing uploads, membership changes, key issuance and publication cannot reopen the Project or create later usable effects.
4. Stop its applications and revoke their keys before physical cleanup. Failed or uncertain shutdown keeps the block and original obligation visible for recovery.
5. Delete known-owned data in bounded resumable steps, respecting source-derived evidence, shared storage relationships, late writes and explicit erasure rules. Data outside the Project stays untouched.
6. Record the actual outcome. Losing a response is not proof of rollback. Inspect the original operation before retrying.

The worker continues the exact deletion that was admitted even when ordinary membership changes. It does not depend on a cached initiating-user permission snapshot, restore the Project or gain authority over another one. This accepted cleanup boundary does not select the unresolved authority model for ordinary paid background work.

## Distinguish progress from completion

| Observable meaning | What the caller may infer |
| --- | --- |
| Deletion admitted and access blocked | The guarded shutdown/erasure obligation exists, not that bytes are gone. |
| Application/key shutdown unfinished | Product access stays blocked while the original shutdown continues or is reconciled. |
| Physical cleanup unfinished | Known removal work remains. Late writes cannot restore use or publication authority. |
| Physical cleanup complete | The owning cleanup completion requirements were established, subject to separately disclosed provider/backup limits. |

These are required meanings, not a new public enum or another job state machine. The [logical deletion-status contract](../../inframeld-application-contracts/references/operation-recovery-contracts.md#deletion-status-inspection) specifies the bounded permitted projection. HTTP route/DTO names and the independently pending retention periods remain delivery work. An unavailable cleanup dependency never permits reporting success or reopening access to meet a timing goal.

<a id="unresolved-protected-status-wording"></a> <a id="preserve-a-narrow-way-to-observe-deletion-completion"></a>

## Read retained status through the original initiating human

[ADR-0080](../../../../docs/adr/ADR-0080-limit-product-deletion-status-to-the-initiating-human.md) resolves the former viewer conflict. Only the currently eligible original initiating human may read the retained content-free product result through the authoritative original principal/operation binding. Ordinary Project membership may already have disappeared.

Administrator status alone grants no access. Other principals cannot claim this exception using an operation ID. Return no private inventory, hidden names, private-content counts or excerpts. The read grants no cancellation or continuation, recreates no grants and restores no resource.

If Alice becomes suspended, retired, recovery-blocked or otherwise ineligible, the exception cannot authenticate or authorize her. Credential expiry/revocation and retained-history limits still apply. Separate host maintenance/diagnostics remain their own protected operations, not a product credential fallback or general administrator browser.

## Failures and changed state

If deletion commits before an upload or publication, the later attempt must observe the block and fail without making that Project usable again. If guarded admission fails, rollback removes its partial block, reservation and audit effects. Once admitted, interrupted or uncertain shutdown/cleanup preserves the committed block and original obligation.

Erasure can invalidate old releases, expected passages, answers and retained evidence. A historical reference does not authorize reconstruction from a newer document or another paid embedding run. Shared-data reuse is not authority to keep erased content. External copies and restored backups follow their separately qualified restrictions.

<a id="keep-project-admission-separate-from-physical-cleanup"></a>

### Keep project admission separate from physical cleanup

Alice may delete Legal Research without being able to read its private HR documents. Access admission checks her current membership and Delete project permission, blocks the project and arranges application/key shutdown. It supplies a durable handoff that names the exact project. Knowledge cleanup consumes that trusted handoff. It does not require Alice to acquire Delete documents on every audience or Delete application account on each application.

Deleting one Document in a surviving project remains different: check Delete documents on every current audience group before committing that Document's marker. A caller cannot select the whole-project worker path by supplying a deletion marker or claiming that admission already happened.

Admission, confirmed access blocking and physical completion are separate reported facts. If cleanup stops after membership removal, the project stays blocked and the original operation records the unfinished steps. Protected job status exposes only safe progress to eligible readers, not private contents or general historical job payloads. It does not implicitly authorize cancellation or continuation. The [logical recovery reference](../../inframeld-application-contracts/references/operation-recovery-contracts.md) defines the accepted observation and recovery boundaries. Native HTTP delivery and runtime recovery checks remain prerequisite engineering work. This guide does not claim the deletion workflow has been implemented.

<a id="example-delete-a-project-while-its-embedding-job-is-running"></a>

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

## Sources, implementation and open decisions

This is accepted design, including the approved status-viewer resolution. It does not establish an implemented deletion route or verified physical completion.

- [Explicit source erasure](deletion-and-retention.md) and [ordinary retention/pins](retention-and-pins.md) own those lifecycle distinctions.
- [Access transport boundaries](../../inframeld-access-models/references/grant-contracts.md) preserve current authority, operation identity and safe disclosure.
- [PD-KNOWLEDGE-02](decision-retention-erasure-policy.md) remains pending for retention periods and other open contracts. Its viewer subquestion alone is resolved.
- [Indexing retirement](../../inframeld-indexing/references/retirement-and-erasure.md), [artifact storage](../../inframeld-application-contracts/references/artifact-storage.md) and [restore](../../../../docs/development/operations/restore.md) retain delayed-write and restoration obligations.
