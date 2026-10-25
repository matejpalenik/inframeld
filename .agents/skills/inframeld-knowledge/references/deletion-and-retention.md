# Sharing, deletion and retained evidence

<a id="sharing-deletion-and-retained-evidence"></a>

Alice removes the handbook from a new corpus, changes its audience, or erases it. These actions have different effects. Omission changes future membership. Sharing changes current readers. Erasure removes the Document's versions and can invalidate retained releases and evaluation evidence.

<a id="change-an-audience-deliberately"></a>

## Choose a focused reading task

- For routine expiry and retained dependencies, read [Retention and pins](retention-and-pins.md).
- For Project block, cleanup and retained status, read [Project deletion](project-deletion.md).

## Change an audience deliberately

Historical versions, downloads and citations use current access. Changing a Document's audience requires a human managing every group in the current or proposed allowlist. Each manager must also be an ordinary member of that same group. Reading a document alone does not permit sharing it.

Group deletion is blocked by Document or active upload/source references. Resolve each reference using the owning operation's permissions. Deleting a group must not cascade into document deletion or silently replace defaults.

<a id="follow-erasure"></a>

## Follow erasure

1. Require Delete documents on every group in the current nonempty allowlist. Add and Update are separate permissions.
2. Record a scoped deletion marker under current authority. Block protected access and publication before physical cleanup begins.
3. Use the existing durable, reference-aware cleanup workflow. Preserve enough progress to resume after interruption without creating another deletion engine.
4. Keep late jobs from republishing erased inputs. Shared vectors needed by other versions follow their exact reference rules.
5. Report affected historical inputs as unavailable rather than silently substituting another corpus or reconstructing deleted evidence.

A retention pin means admitted or retained work still needs an artifact. Ordinary expiry respects pins. Explicit erasure can invalidate them. Immutability preserves identity and provenance, not content forever.

For Evaluation, source replacement must not retarget an old expected passage. Source erasure can make questions, references or protected evidence unavailable.

<a id="ownership-and-failure-behavior"></a>

## Ownership and failure behavior

Removing Alice's account does not itself delete shared project documents. Application-account retirement preserves required attribution without reassigning its actions to a human.

Whole-project deletion has its own human-only authority and scope. It can erase project-owned private content without granting the deleter reading rights. Individual-resource deletion in a surviving project keeps its ordinary checks.

After a deletion marker commits, an interrupted cleanup remains blocked and resumable. One observation of physical absence does not establish final cleanup when delayed writes are possible. Indexing owns numerical tombstones and completion barriers. Knowledge must not declare them complete merely because document admission is blocked.

<a id="change-sharing-defaults-or-availability"></a>

<a id="changes"></a>

<a id="5-change-sharing-defaults-or-availability"></a>

## Change sharing, defaults, or availability

Every document keeps at least one allowed group. Changing that list requires a human who manages every old and new group. The current list also protects historical versions and citations. A group cannot be deleted while active configuration refers to it, and source-system permissions do not replace Inframeld permissions.

Private defaults are ordinary project resources. Changing them needs Manage upload defaults and management of every old and new default group. Only future uploads are affected. Each upload still needs Add documents on every selected group, with no fallback to a less restricted audience.

A complete, authorized upload batch can request an update for the **whole selected corpus**, including unchanged documents. A partial batch, saved draft, or upload-only permission cannot publish. The newest eligible request replaces older publication requests. [Onboarding](../../inframeld-architecture/references/first-use-and-private-defaults.md) and [Releases](../../inframeld-pipelines/references/configuration-queries-and-builds.md) define that workflow.

Leaving a document out of a new revision, changing its audience, and deleting it do different things. Deletion covers all versions and needs Delete documents on every current group. Access is blocked first, then cleanup can resume in stages. A late job cannot restore it. See [retention and deletion](./deletion-and-retention.md).

<a id="block-access-before-cleanup"></a>

<a id="operation"></a>

<a id="2-block-access-before-cleanup"></a>

## Block access before cleanup

Use the following sequence for an authorized deletion:

1. **Check who may delete what.** Authenticate the caller, check the required permission, and establish exactly which owned data the request covers.
2. **Record the deletion marker and cleanup obligation.** Commit the authoritative block, audit and recoverable operation consistently. A tombstone records that the scope may no longer be used. It does not mean its bytes are already gone. Block new access and work, and invalidate affected serving references before removing bytes.
3. **Establish shutdown and account for unfinished work.** For whole-project deletion, stop its applications and revoke their keys before data cleanup. Cancel or reconcile queued and running jobs. Every later publication must check the marker, so a late job cannot make the data available again. This cannot cancel a request already accepted by another storage service.
4. **Remove owned data.** Delete artifacts and derived data in limited-size steps that can safely repeat. Save progress. All Chroma deletion uses the [existing single vector writer](../../inframeld-indexing/references/profiles-and-preparation.md).
5. **Handle remaining identity and audit references.** Remove or anonymize them as required by the admitted scope. Project deletion does not delete its members' shared Kratos/Hydra identities or affect other projects. Any separately authorized identity deletion uses the selected adapter for its remaining session/credential cleanup. Project application shutdown has already happened before step 4.
6. **Report what actually finished.** Mark deletion complete only after every supported step in scope succeeds. Otherwise return the defined outcome for the unfinished step.

Each step must limit how much work it does at once. Retrying it must neither expand the deletion scope nor repeat its logical effect. These properties make cleanup bounded and idempotent.

<a id="delete-only-known-owned-data-and-preserve-valid-shared-references"></a>

### Delete only known-owned data and preserve valid shared references

A **vector generation** identifies one fixed set of embedding output. Several compatible materializations can share that generation.

Before removing a shared artifact or generation, check who owns it and which retained materializations still need it. **Unknown ownership is not permission to delete. Ending one reference does not end the others.**

For example, retiring one materialization does not justify removing vectors that another retained materialization still needs. Explicit source erasure follows the different rule in [Protect required artifacts from routine expiry, not explicit erasure](retention-and-pins.md#protect-required-artifacts-from-routine-expiry-not-explicit-erasure): invalidate the affected serving state first rather than retain that source indefinitely for rollback.

Every Chroma deletion goes through the [single vector-writer component](../../inframeld-indexing/references/profiles-and-preparation.md), including deletion jobs. “Single” means one owner of writes, not a new service.

<a id="report-physical-cleanup-honestly"></a>

<a id="completion"></a>

<a id="3-report-physical-cleanup-honestly"></a>

## Report physical cleanup honestly

PostgreSQL can prevent access and publication without being able to cancel a write already executing in another store. Both Chroma and SeaweedFS need explicit handling for that case.

<a id="authorize-history-and-completion-status"></a>

<a id="history"></a>

<a id="4-authorize-history-and-completion-status"></a>

## Authorize history and completion status

Check current permissions every time someone reads a receipt or result, including a repeated request. Knowing an old request key or pipeline ID cannot restore revoked access.

V1 authorizes documents through group allowlists. Integrations use their application account's own configured access. A caller-supplied user ID cannot change that authority.

The access model distinguishes the verified actor from a possible **delegated subject**, a user it would be verified to represent. That leaves room for future delegation without implementing it in v1.

**Never release revoked source content or citations because a historical pipeline, receipt, or idempotency record once referred to them.** Apply current authorization at the established access-check boundary.

<a id="preserve-a-narrow-way-to-observe-deletion-completion"></a>

### Preserve a narrow way to observe deletion completion

Deleting an account or project can remove the memberships normally needed to see its jobs. The person authorized to request deletion must still have an authorized way to find out whether it finished.

A retained product deletion-status result is available only to the currently eligible original initiating human through its original principal/operation binding. [ADR-0080](../../../../docs/adr/ADR-0080-limit-product-deletion-status-to-the-initiating-human.md) rejects administrator status alone. The result contains no private Project content and grants no cancellation or continuation.

The account-deletion and authentication flow must support that narrow status check. Former membership does not give permanent access to all historical project jobs or their contents. The exact endpoint and account flow remain implementation decisions.

Feedback follows its answer receipt's eligibility and retention period. It does not keep vectors alive. When the receipt expires, remove its rating and comment. Source or project erasure removes or redacts affected comments. Authorization must check every source in the final answer context, even evidence the answer did not cite. See the [feedback lifecycle](../../inframeld-pipelines/references/answer-feedback.md#lifecycle).

<a id="explain-remaining-external-copies"></a>

<a id="external"></a>

<a id="6-explain-remaining-external-copies"></a>

## Explain remaining external copies

The selected model connection determines where document content goes for external processing. Sending data outside the application environment is called **data egress**.

| Operation | Content or processing boundary to disclose |
| --- | --- |
| **Document embedding** | Chunk text goes to the selected model gateway. A chunk is a document excerpt prepared for retrieval. |
| **Answer generation** | The query and permitted source excerpts go to the selected generation connection through the gateway. |
| **Starter-case generation** | The sampled permitted passages and persona guidance go through the gateway to the explicitly selected generator, including extraction/synthesis steps. Generated references remain protected derived content. |
| **Evaluation judging** | Any selected judge has its own explicitly disclosed evidence payload through the same gateway. A judge is a model that evaluates an answer. |
| **Future Chroma Cloud use** | An external-processing option for future EE, not a selected v1 requirement. |

Customer-controlled remote endpoints can have their own logging and retention. Inframeld cannot universally promise to erase those external copies merely because it deleted the local source.

A user-visible deletion result must state **which application-controlled stores were cleared, which supported steps remain unresolved, and what external or backup limits remain**.

Do not imply that Inframeld can delete history from every provider. Add a provider-specific integration only when the selected provider offers a relevant supported mechanism.

A deletion endpoint implements these technical boundaries. **It does not, by itself, establish privacy or legal compliance**, which is broader than this architecture.

<a id="maintainer-checks"></a>

<a id="7-maintainer-checks"></a>

## Maintainer checks

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

<a id="pending-decisions-for-dependent-implementation"></a>

## Pending decisions for dependent implementation

Before choosing an unresolved implementation contract, load only the entry whose trigger applies:

- [PD-KNOWLEDGE-02: Choose bounded retention without weakening explicit erasure](decision-retention-erasure-policy.md). Before implementing retention configuration, bounded history storage, expiry or cross-domain source-erasure cleanup.
- [PD-INDEXING-04: Qualify frozen storage retries and final erasure barriers](../../inframeld-indexing/references/decision-storage-retries-and-erasure.md). When implementing frozen-write retry/retirement adapters, selecting artifact completion mechanics or qualifying final-erasure claims.

## Status, sources and unresolved scope

<a id="status-and-sources"></a>

The erasure and audience rules are accepted design. Exact retention periods and every cleanup/storage protocol are not qualified by this explanation. Use existing code and attributed evidence when answering what works today.

- [Retention and deletion](./deletion-and-retention.md), [blocking before cleanup](#operation), [Knowledge sharing](documents-and-collections.md) and [Access group managers](../../inframeld-access-models/references/memberships-groups-and-handover.md#group-managers).
- [Group relationship constraint](../../inframeld-access-models/references/access-lifecycle-persistence.md#group-manager-membership-constraint), [protected evaluation history](../../inframeld-evaluation/references/history-and-dataset-transfer.md#history) and [Indexing retirement](../../inframeld-indexing/references/retirement-and-erasure.md#retirement).
- [Maintainer lifecycle checks](uploads-and-source-sync.md#maintainer-checks) cover replacement, retry, changed audiences and deletion races.

<a id="decision-and-reference-map"></a>

<a id="decision-map"></a>

<a id="8-decision-and-reference-map"></a>

Exact retention periods, erasure/anonymization policy, and the narrow deletion-status endpoint still need implementation decisions. [Recovery](../../../../docs/development/operations/restore.md#restrictions) owns the provisional off-host restriction register. Explicit erasure can make an old release unavailable. Keeping its history does not require retaining its content forever or guarantee deletion from every provider and backup.

| Decision | Rationale |
| --- | --- |
| [ADR-0039](../../../../docs/adr/ADR-0039-block-access-before-resumable-physical-deletion.md) | Block access before resumable physical deletion. |
