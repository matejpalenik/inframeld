# Preserve Access relationships through lifecycle changes

Alice wants to stop managing SupportKnowledge but keep reading its documents. Demotion removes her management assignment while preserving ordinary membership. Removing membership, suspending Alice and deleting the group have different effects.

**Status:** these are accepted lifecycle and persistence requirements. The manager-membership foreign key is implemented. That constraint does not establish implemented appointment, handover, departure, retirement or Project-deletion workflows. Exact database definitions remain in [Access persistence](access-persistence.md).

## Apply one guarded write

1. Authenticate the caller and identify the requested operation and exact scope. An identity or resource ID does not establish permission.
2. Inside the owning application's short transaction, acquire the required [Organization/Project coordination](grant-administration.md#how-the-database-gives-each-change-its-turn). Check current eligibility, exact authority and handover under the owning workflow's rules.
3. Follow the operation's original-request recovery contract. An authorized completed replay returns its recorded outcome without another change. For new work, check the required reviewed revision before applying the relationship changes below. Save the actual change, revision, required audit and safe original outcome together.
4. Let the application-owned transaction commit or roll back together. External calls stay outside it. A denial or stale review cannot leave partial local assignments.

For appointment, ordinary membership and management must agree. A foreign key protects the relationship, while the application establishes permission and safe handover. See [Memberships and handover](memberships-groups-and-handover.md) for the full human workflow. The following sections specify the persistence effects rather than another authorization engine.

<a id="group-manager-membership-constraint"></a>

<a id="every-group-manager-requires-ordinary-membership"></a>

## Every group manager requires ordinary membership

The [25 September 2026 decision](../../../../docs/adr/ADR-0049-require-group-managers-to-be-ordinary-members.md) requires each manager assignment to reference ordinary membership for the same `(project_id, group_id, principal_id)`. Alice therefore has two records when she manages a group. Removing management can leave her an ordinary member. Membership alone does not make someone a manager.

The implemented `group_managers` table has a foreign key from that three-column key to the matching `group_memberships` primary key. Keep its human-only check and scoped project-membership reference too. The database must reject removing membership while the manager row remains.

When an authorized operation removes both, it checks handover and removes management first. Automatic cascading deletion cannot replace those checks or the audit record.

Creating a group, appointing a manager, or recovering a stranded group saves both assignments together. Demotion removes only management. Removing membership also removes management, and rejoining does not restore it. Save each change, scope revision, and audit event in the same protected Access transaction. See the [group workflow](memberships-groups-and-handover.md#group-managers).

Suspension keeps both records but blocks their use. Foreign keys cannot prove that Alice is active, may make this change, or will leave another eligible manager. Application policy still checks those conditions. The initial migration implements the membership constraint, and the PostgreSQL constraint tests exercise it. The surrounding administration workflows remain to be implemented.

<a id="deletion-and-retention-behavior"></a>

## Deletion and retention behavior

Live foreign keys should normally **restrict parent deletion**. The authorized use case checks handover, removes the affected current rows in order, and records the audit event. This makes the cleanup explicit instead of hiding an authorization workflow in database cascades. Whole-project cleanup still marks deletion first and resumes through jobs.

| Change | Required persistence effect |
| --- | --- |
| Appoint a manager or create a group | Insert any missing ordinary membership and the manager assignment together. Preserve existing membership, recheck eligibility, advance the scope revision, and audit in the same transaction. |
| Demote a manager | Remove only the manager assignment after required handover checks. Retain ordinary membership, advance the scope revision, and audit together. |
| Remove group membership | After handover checks, remove any manager assignment before the membership in the same transaction, with revision and audit. Readding membership does not restore management. |
| Recover a stranded group | Record the eligible replacement's ordinary membership and management together under scoped operator recovery, with revision and audit. Keep the compromised principal blocked. |
| Suspend a human | Change principal status and preserve both membership and management, plus other grants. Block reading and administration immediately, even for the sole manager. Record the status change and audit together under installation write coordination. |
| Remove a human from a project | After handover checks, remove that recipient's project/group/application/resource grants, manager assignments before group memberships, then project membership. Audit together. Do not delete grants merely because this human assigned them. |
| Revoke or downgrade a grant | Delete the current row or update `can_grant`. Bump the scope revision and audit together. A later regrant is a fresh assignment with fresh attribution. |
| Delete an unused group | Check all current Document, active-upload, default and source references, then remove its manager assignments before memberships, its own grants, and the group. Reference FKs prevent dangling or cross-project relationships. A default group must be replaced through its authorized configuration workflow first. |
| Delete an application | Retire its principal, revoke keys, remove its received grants/group relationships/project membership and human grants targeting the account. Retain only the inert identity/account/credential metadata justified by retention, then purge in dependency order. Do not delete project data it created. |
| Delete a project | First make the project unavailable to new work, stop its applications and revoke their keys, then clean up project data and access records under the accepted deletion lifecycle. No handover is needed for a scope being deleted. Historical audit is handled by retention, not by a blanket project cascade. |

## Failures, concurrency and limits

The table assumes the owning operation has passed its current checks. A foreign-key constraint cannot authorize the caller or decide that another eligible manager remains. A failure before commit rolls back local relationship, revision and audit effects together. Committed deletion blocks and later external cleanup retain their original [Project-deletion workflow](../../inframeld-knowledge/references/project-deletion.md). Physical erasure is distinct from removing Access rows.

## Sources

[ADR-0049](../../../../docs/adr/ADR-0049-require-group-managers-to-be-ordinary-members.md) owns the member-plus-manager invariant. [The initial migration](../../../../apps/backend/migrations/versions/0001_initial.py) owns its foreign key. [Grant administration](grant-administration.md) owns coordinated writes, [membership/handover](memberships-groups-and-handover.md) owns safe departure, and [retention](../../inframeld-knowledge/references/deletion-and-retention.md) owns surviving history. Current application-key and erasure qualifications remain unchanged.
