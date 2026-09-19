# ADR-0014: Retention, scoped deletion, and external processing

**Status:** Accepted — security and retention boundaries; precise retention defaults remain implementation work.
**Revised:** 19 September 2026.
**Required approach:** Ownership-scoped, resumable deletion that blocks access before physical cleanup, applies current permissions to historical records, and reports backup and external-processing limits explicitly.
**Related:** [Access](ADR-0005-api-enforced-tenancy-and-authorization.md), [model gateway](ADR-0006-byok-provider-boundary.md), [durable jobs](ADR-0007-durable-jobs-idempotency-and-recovery.md), [recovery](ADR-0013-minimal-hosted-observability-and-recovery.md).

## Context

Inframeld retains documents, their processed and indexed versions, evaluation evidence, and records of application operations. Some of this data belongs to a user; some belongs to a project shared with other people. Copies can also exist in backups or at an external model endpoint that processed the content.

These records have different lifecycles. Removing a user’s account must not silently remove a project’s knowledge. Routine expiry must not delete an index that a live release still needs. An explicit erasure request, however, must not leave content accessible merely because an older pipeline refers to it.

From first principles, **ownership, permission to read, and the presence of stored bytes are separate questions**. Blocking access can happen before physical cleanup finishes. Deleting an application-controlled copy does not establish that every backup or external provider has erased its copy too.

This decision defines how Inframeld handles those distinctions without retaining sensitive data indefinitely or presenting incomplete cleanup as completed erasure.

## Decision

**Use the existing durable jobs to delete authorized user-scoped and project-owned data. Record a deletion tombstone and block access first, then clean up only the data within the established ownership scope. Recheck current permissions on historical reads and report any unresolved cleanup steps.**

A **tombstone** is a durable record that an identity or scope has been deleted or retired. It prevents new access, work, or publication from making that data available again while its stored bytes are being removed.

This design uses the selected SeaweedFS artifact storage, Kratos identity integration, group allowlists, fixed integration access, and immutable vector generations. It does not reopen those choices. The backup operating model and numerical estimates remain provisional; exact retention policy and future organization-administration packaging remain separate decisions. Product-level index reconstruction and permanent numerical archives remain deferred.

### 1. Separate user data from project ownership

**Scope** identifies exactly whose data and which resources an operation may affect. Keep three categories distinct:

| Category                                        | Ownership and deletion rule                                                                                                                                                    |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **User identity, profile, and session records** | Handle through the account-administration flow, Kratos, and the application’s authorization rules. Removing a user is not an instruction to delete shared project data.        |
| **Project-owned knowledge and releases**        | Belong to the project, not automatically to the individual who uploaded or created them. Delete them only through an authorized operation for that ownership scope.            |
| **Bounded operational records**                 | Jobs, receipts, idempotency records, audit evidence, and logs follow their defined retention and erasure rules. They are not an unlimited archive of user activity or content. |

For example, Mira can upload a manual into a shared project. Removing Mira’s account does not, by itself, delete that project’s manual or the versions other members use.

The application supports **authorized, resumable deletion** of owned project data and user-scoped data through its existing durable jobs. Resumable means the operation can continue after an interruption rather than depend on one uninterrupted request.

A last administrator must not accidentally leave shared ownership without an administrator. Require an authorized ownership transfer or an explicit project/workspace deletion procedure.

An organization ownership boundary exists internally for future **Enterprise Edition (EE)** capabilities. This does not require a multi-organization software-as-a-service signup or administration product in v1. Organization-administration packaging and exact endpoints remain separate scope decisions.

### 2. Protect required artifacts from routine expiry, not explicit erasure

**Retention** defines how long records are kept and when routine cleanup may remove them. Document the configuration defaults for sources, immutable processing/materialization artifacts, evaluations, answer receipts, jobs, idempotency records, and logs. This ADR does not assign their exact retention periods.

An **artifact** is stored content such as a source file, processing output, or manifest. A **materialization** is the prepared searchable index bound to exact source versions and processing settings. A **Deployment** selects which pipeline version serves requests.

Some references temporarily prevent routine expiry. These are **pins**: records that an artifact is still required.

| Situation                                                        | Required behavior                                                                                                                                                                          |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Current, candidate, or designated previous Deployment target** | Pin the artifacts that target needs. Current serves requests, candidate is being tried, and the designated previous target is retained for rollback. Routine expiry must not break them.   |
| **Admitted query**                                               | Temporarily protect the selected immutable artifacts while the accepted query uses them. Admission means the application has accepted the operation for execution.                         |
| **Explicit source erasure or security deletion**                 | Invalidate affected serving state first, then follow the deletion procedure. Retention pins do not override the erasure action. Explain why an affected historical version is unavailable. |

**An immutable version is not a promise to keep its content forever.** Its recorded identity must not be silently rewritten, but explicit erasure can remove data it needs to serve.

### 3. Keep audit and retry records useful without turning them into content archives

Audit records are **append-only during normal operation**: ordinary actions add evidence rather than rewrite earlier events. That does not require retaining personal data forever.

Keep only the necessary actor, action, resource, time, and outcome evidence, subject to defined erasure or anonymization. The **actor** is the verified human or application that performed the action. Anonymization removes identifying information according to the applicable policy; this ADR does not define the precise policy.

Full source text, prompts, credentials, and model responses must not enter operational logs.

An **answer receipt** records bounded information about an answer execution, not a cache of the whole answer. Likewise, an **idempotency record** lets the application recognize a retry of the same requested operation; it is not permission to retain the original sensitive response indefinitely.

[ADR-0007](ADR-0007-durable-jobs-idempotency-and-recovery.md) defines sanitized retry outcomes and the absence of durable full-query replay. Sanitized outcomes contain the safe information needed to report the operation without replaying secrets or a stored full production answer.

### 4. Tombstone first, then perform resumable cleanup

Use the following sequence for an authorized deletion:

1. **Establish the exact scope.** Authenticate the caller, authorize the operation, and determine the ownership boundary of the data to delete.
2. **Commit the deletion tombstone.** Block new access and work for that scope, and invalidate affected serving references before physical cleanup begins.
3. **Cancel or reconcile pending work.** Account for queued and active jobs. Every later publication checks the tombstone, so a late job cannot republish or reauthorize deleted data. This does not cancel a storage request already accepted outside PostgreSQL.
4. **Delete owned artifacts and derived state.** Use bounded, idempotent steps and preserve progress for resumption. All Chroma deletion goes through the existing single mutation owner specified in ADR-0004.
5. **Clean up applicable identity and audit references.** Remove or anonymize them as required, and revoke relevant credentials and sessions through the selected identity adapter.
6. **Report the actual result.** Complete only when every supported in-scope step has succeeded. Otherwise expose a typed unresolved step: a defined outcome identifying what remains unfinished rather than a false success.

**Bounded** steps handle a limited amount of work at a time. **Idempotent** steps can be retried without repeating their logical effect or expanding the deletion scope.

#### Example: delete a project while its embedding job is running

An embedding job converts document text into numerical search vectors. Suppose project deletion starts after the job has sent a request to the model provider.

```text
Project deletion commits its tombstone
    -> New project access and work are blocked
    -> The already-sent external call may still finish
    -> The job checks publication authority and sees the tombstone
    -> Publication is rejected
    -> Owned outputs are handled by the deletion/cleanup procedure
```

The completed external call does not make its result eligible for publication. Cleanup uses the existing vector writer; the deletion job does not become another process racing to mutate the same shared vectors.

### 5. Delete only known-owned data and preserve valid shared references

A **vector generation** identifies one immutable set of numerical embedding output. Compatible materializations can share its vectors rather than store separate copies.

Before cleanup removes an artifact or vector generation, establish its ownership and check whether another retained materialization still requires it. **Do not delete data whose ownership is unknown, or remove a shared vector merely because one reference to it has ended.**

For example, retiring one materialization does not justify removing vectors that another retained materialization still needs. Explicit source erasure follows the different rule in Section 2: invalidate the affected serving state first rather than retain that source indefinitely for rollback.

All Chroma deletions use the **singleton mutation owner** in [ADR-0004](ADR-0004-postgresql-source-of-truth-and-shared-chroma.md). Singleton here means there is one designated component responsible for vector mutations, not a separate deletion writer introduced by this workflow.

### 6. Distinguish revoked access from completed physical deletion

PostgreSQL can prevent access and publication without being able to cancel a write already executing in another store. Both Chroma and SeaweedFS need explicit handling for that case.

#### A delayed Chroma insert can arrive after deletion

An old immutable insert may remain unresolved after its client stops waiting. The following sequence is possible:

```text
An insert is sent; its completion remains unknown
    -> The generation is tombstoned and its records are deleted
    -> A read currently finds no records
    -> The old insert finishes and recreates an unreachable record
```

The recreated record must remain inaccessible. PostgreSQL tombstones and current **server-owned generation filters** exclude it from queries. Those filters are built by the application from the permitted generation set, not supplied by the caller.

**Tombstoned physical IDs are never reused.** A late insert cannot make the retired generation eligible for a new build or serving request.

However, an absence read only establishes that the record was missing when checked. It does not prove an unresolved write will never recreate it. Report **“Access revoked; physical cleanup pending”** until the write-completion or quiescence evidence permits final cleanup.

**Quiescence** means establishing that earlier work can no longer arrive after the final cleanup. Retain unresolved-attempt evidence and allow automatic garbage collection (GC) to retry cleanup within the bounded procedure. GC is the removal of data that is no longer needed.

Ordinary candidate-write retries do not require restarting Chroma. Exceptional final cleanup of unresolved writes may need maintenance, operator action, or provider assistance under ADR-0004. These are different recovery situations.

#### A delayed SeaweedFS upload has the same problem

A SeaweedFS `PUT` uploads a source, artifact, or retry payload. If it is still in flight, it may finish after an earlier deletion and recreate bytes even though PostgreSQL will never publish their reference.

Use immutable, scoped attempt keys, so each upload has a known ownership scope and physical attempt identity. Retain evidence of unresolved uploads.

Do not report final physical deletion until completion or quiescence and final cleanup are established. **A PostgreSQL check prevents application access and publication; it does not cancel a remote object-store request.**

### 7. Check current access on historical reads and deletion status

Recheck current authorization whenever a caller reads a receipt or result, including an idempotency replay. Remembering a request key or finding a historical pipeline reference must not restore a revoked permission.

V1 uses **group allowlists**, which identify groups permitted to access documents, and **fixed integration authority**, under which an application uses its own configured access. Caller-supplied user IDs never change that scope.

The access boundary distinguishes a verified actor from an optional **delegated subject**, a user the actor would be verified to represent. This accommodates future verified delegation without implementing it now.

**Never release revoked source content or citations because a historical pipeline, receipt, or idempotency record once referred to them.** Apply current authorization at the established access-check boundary.

#### Preserve a narrow way to observe deletion completion

Deleting an account or project may remove the memberships ordinarily used to authorize its job history. The deletion flow must still preserve an authorized way to observe completion.

A deletion job may expose a **minimal deletion-status receipt** to its original authorized actor or an administrator. That receipt reports progress or unresolved steps without reopening deleted project content.

The selected authentication/account-deletion flow must support this observation path. Do not use already-deleted memberships as a reason to expose all historical project jobs, or treat original membership as a permanent grant to their contents. The exact endpoint and account-flow details remain implementation decisions.

### 8. Give answer feedback the same lifetime and evidence protections as its receipt

The feedback feature extends the existing bounded serving receipt with a current rating and comment. It does not introduce a permanent feedback archive.

| Event or constraint                | Required feedback behavior                                                                                                                                                 |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Eligibility and retention**      | The current rating/comment shares its receipt’s eligibility and retention window. Feedback does not extend that window or pin vectors.                                     |
| **Stored content**                 | Do not add full production query or answer bodies to support feedback.                                                                                                     |
| **Reading a comment**              | Check all source identities bound to the final generation context, including uncited evidence. A comment may quote a source that did not appear in the answer’s citations. |
| **Receipt expiry**                 | Remove the associated feedback as part of the expiry.                                                                                                                      |
| **Source or project erasure**      | Remove or redact affected comments. Tombstones deny access while cleanup proceeds.                                                                                         |
| **Ordinary permission revocation** | Change access at the established current-authorization check boundary without rewriting the historical serving version.                                                    |

The **final generation context** is the selected evidence supplied to the model to produce the answer. Its complete source-identity set matters even when only some sources were cited.

[ADR-0017](ADR-0017-answer-feedback.md) defines the accepted feedback contract and denominators: the populations counted when reporting feedback statistics. This ADR preserves that contract’s retention boundary; it does not select a new permanent archive.

### 9. Prevent backup restoration from restoring deleted content or revoked access

The supported restore procedure must account for restrictions imposed **after** the selected backup was taken.

For example, restoring a backup from before a document was deleted must not make that document available again. Restoring an older group membership must not restore permission that was subsequently revoked.

[ADR-0013](ADR-0013-minimal-hosted-observability-and-recovery.md) proposes a separately protected operator register of restrictive changes and deletions, conservative access denial where its coverage is incomplete, and invalidation of restored sessions and credentials. This operating mechanism is a **provisional baseline for validation and refinement**, not a requirement to build an automatic journal service.

Keep affected scopes closed until current restrictions and the required treatment of deleted content have been established. A restored database’s historical state is not sufficient authority to reopen access.

Document backup expiry and the limits it creates. **Do not claim that a deletion request immediately modifies every immutable backup.** The deletion result must distinguish cleanup of live application-controlled stores from remaining backup copies and their retention policy.

### 10. Disclose external processing and the limits of deletion

**Data egress** means data leaving the application environment for processing elsewhere. The selected model connection determines where these operations send content.

| Operation                   | Content or processing boundary to disclose                                                                                                  |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **Document embedding**      | Chunk text goes to the selected model gateway. A chunk is a document excerpt prepared for retrieval.                                        |
| **Answer generation**       | The query and permitted source excerpts go to the selected generation connection through the gateway.                                       |
| **Evaluation judging**      | Any selected judge has its own explicitly disclosed evidence payload through the same gateway. A judge is a model that evaluates an answer. |
| **Future Chroma Cloud use** | An external-processing option for future EE, not a selected v1 requirement.                                                                 |

Customer-controlled remote endpoints can have their own logging and retention. Inframeld cannot universally promise to erase those external copies merely because it deleted the local source.

A user-visible deletion result must state **which application-controlled stores were cleared, which supported steps remain unresolved, and what external or backup limits remain**.

Provider-specific historical deletion integrations are not automatically required for every provider. Add one only when a selected provider exposes a relevant supported mechanism; do not imply that a general integration exists already.

A deletion endpoint implements these technical boundaries. **It does not, by itself, establish privacy or legal compliance**, which is broader than this architecture.

### 11. Verify deletion, replay, and restore behavior

These are acceptance requirements, not evidence that the implementation has passed them.

| Area                               | Required verification                                                                                                                                                                              |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Ownership and scope**            | Deny cross-scope deletion. Removing a user must not silently delete project-owned knowledge, and the last administrator must not orphan shared ownership.                                          |
| **Tombstone ordering**             | Commit the tombstone and block affected access/work before cleanup. A late job must fail its publication check.                                                                                    |
| **Shared vectors**                 | Preserve vectors still needed by another retained materialization. Route every Chroma deletion through the designated mutation owner.                                                              |
| **Crash recovery**                 | Interrupt deletion and resume its bounded, idempotent steps without expanding scope or losing unresolved-step visibility.                                                                          |
| **Late external writes**           | Exercise delayed Chroma inserts and SeaweedFS uploads after deletion. Keep them inaccessible and report physical cleanup as pending until completion/quiescence and final cleanup are established. |
| **Current authorization**          | Deny revoked receipt/result access and idempotency replay. Verify group allowlists, fixed integration authority, and scoped opaque credentials rather than trusting caller-supplied identities.    |
| **Content minimization**           | Keep secrets and full production answers out of replay caches, and source text, prompts, credentials, and model responses out of operational logs.                                                 |
| **Feedback**                       | Check uncited final-context sources, expire feedback with its receipt, and remove/redact affected comments on erasure without creating a permanent archive.                                        |
| **Account and storage procedures** | Validate the selected Kratos and SeaweedFS procedures, including an authorized way to observe deletion completion without reopening deleted content.                                               |
| **Backup restore**                 | Restore a backup that predates a deletion tombstone and verify that current restrictions and deleted-content exclusion remain enforced.                                                            |

Exact retention defaults and erasure/anonymization policies still need implementation decisions. Provisional backup operating targets, future organization packaging, and finer access-control lists (ACLs) remain distinct from these accepted deletion and security requirements.

## Consequences

### Positive

- **Deleting a user does not accidentally delete shared knowledge.** Explicit ownership scope and the last-administrator guard keep account administration separate from project deletion.
- **Access protection does not wait for every physical store to finish cleanup.** Tombstones and current authorization prevent late jobs, historical references, and retries from making deleted or revoked content available again.
- **Deletion remains observable and limited to what the application can establish.** Durable progress, shared-reference checks, bounded receipts, and explicit backup/provider limits avoid pretending that one successful delete erased every copy everywhere.

### Negative

- **Deletion requires more than removing database rows.** The implementation must coordinate jobs, serving references, shared vectors, identity state, feedback, and storage cleanup while preserving safe progress visibility.
- **Physical cleanup can remain unresolved after access is blocked.** Late external writes may require repeated cleanup or exceptional maintenance/operator/provider assistance. An absence check alone is insufficient evidence of final erasure.
- **Recovery and external retention limit the result.** Restores need current restriction evidence before access resumes, backups expire under a documented policy, and remote processors may retain data outside Inframeld’s control. Precise retention and erasure defaults still need definition.

## Alternatives considered

No separate comparative evaluation is recorded. The approaches below are excluded or not required by this decision.

### Cascade account deletion into all documents the user created

**Ruled out.** Project knowledge and releases belong to their ownership scope, not automatically to their creator’s account. Shared ownership requires an authorized transfer or explicit project/workspace deletion rather than an accidental cascade.

### Apply expiry regardless of live references, or retain referenced data forever

**Neither approach is selected.** Routine expiry respects release and query pins. Explicit security erasure overrides that routine protection by invalidating affected serving state first. Historical references do not guarantee permanent retention or permanent access.

### Delete stored bytes first and block publication afterward

**Ruled out.** Commit the tombstone before cleanup and recheck it at publication. Otherwise active work could make data available again while deletion is in progress. Physical vector cleanup remains with the existing mutation owner, not an independent competing writer.

### Treat one successful delete and absence check as final erasure

**Insufficient while an earlier write is unresolved.** A delayed Chroma insert or SeaweedFS upload can recreate inaccessible bytes. Preserve tombstones and attempt evidence, and report pending cleanup until the relevant completion/quiescence and final cleanup are established.

### Use historical permissions or full-response caches to make retries easier

**Ruled out.** Current authorization applies to results, receipts, and idempotency replay. Sanitized outcomes and bounded answer receipts do not retain full production answers or let a caller recover revoked content through an old request key.

### Promise immediate deletion from every backup and external provider

**Not supported by this design.** Document backup expiry, reconcile newer restrictions before restoring access, and disclose remote retention limits. A general provider-deletion framework or new automatic restriction journal is not implicitly required.

## References

| Reference                                                                                        | Responsibility                                                                                                                        |
| ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| [ADR-0004: Vector storage and cleanup](ADR-0004-postgresql-source-of-truth-and-shared-chroma.md) | Shared immutable generations, the singleton vector mutation owner, delayed-write handling, and final cleanup requirements.            |
| [ADR-0005: Access](ADR-0005-api-enforced-tenancy-and-authorization.md)                           | Kratos integration, group allowlists, fixed integration authority, and current authorization.                                         |
| [ADR-0006: Model gateway](ADR-0006-byok-provider-boundary.md)                                    | Model-call destinations, customer-controlled endpoints, and disclosed data egress.                                                    |
| [ADR-0007: Durable jobs](ADR-0007-durable-jobs-idempotency-and-recovery.md)                      | Resumable work, sanitized idempotency outcomes, and bounded receipts without durable full-query replay.                               |
| [ADR-0013: Recovery](ADR-0013-minimal-hosted-observability-and-recovery.md)                      | The provisional backup/restore operating model, later restriction/deletion reconciliation, and deferred product-level reconstruction. |
| [ADR-0017: Answer feedback](ADR-0017-answer-feedback.md)                                         | Feedback eligibility, receipt-linked retention, evidence access, and reporting denominators.                                          |
