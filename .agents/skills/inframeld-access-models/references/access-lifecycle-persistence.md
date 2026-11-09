# Preserve Access relationships through lifecycle changes

Alice wants to stop managing SupportKnowledge but keep reading its documents. Demotion removes her management assignment while preserving ordinary membership. Removing membership, suspending Alice and deleting the group have different effects.

**Status:** these are accepted lifecycle and persistence requirements. The manager-membership foreign key and guarded Project membership addition/removal are implemented. Group creation, appointment, group-only departure, safe inspection and unused-group deletion are implemented through focused services and migration 0025. The exact-Project application-shutdown [protocol](../../../../apps/backend/src/inframeld_backend/access/application/protocols/project_application_shutdown_effects_writer.py) and [PostgreSQL effects writer](../../../../apps/backend/src/inframeld_backend/access/infrastructure/writers/postgres_project_application_shutdown_effects_writer.py) are implemented and qualified by [twelve local PostgreSQL cases](../../../../apps/backend/tests/integration/access/test_project_application_shutdown_postgres.py). Their caller owns the original deadline, transaction and rollback, revision, audit and original parent checkpoint. These effects do not establish authentic admission or business completion. Public retirement and its pending HTTP completion decision remain under [#233](https://github.com/matejpalenik/inframeld/issues/233), and Project-deletion admission and orchestration remain under [#204](https://github.com/matejpalenik/inframeld/issues/204). Stranded-group repair retains its separate status. Exact database definitions remain in [Access persistence](access-persistence.md).

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

Suspension keeps both records but blocks their use. Foreign keys cannot prove that Alice is active, may make this change, or will leave another eligible manager. Application policy still checks those conditions. The initial migration implements the membership constraint, and the PostgreSQL constraint tests exercise it. Project removal and group-only member removal apply the manager-before-membership order. Current group changes use Organization-shared then Project-exclusive coordination and count only eligible remaining human managers.

<a id="project-membership-original-results"></a>

## Keep original membership results after departure

The [0020 receipt migration](../../../../apps/backend/migrations/versions/0020_project_membership.py) follows `0019_human_admission`. It adds only `project_membership_operation_results`, without changing the existing membership or grant tables. Its [typed row](../../../../apps/backend/src/inframeld_backend/access/infrastructure/rows/project_membership_operation_result_row.py) retains operation ID, installation/Organization/Project scope, actor and recipient principal IDs, add/remove kind, before/result Access revisions, changed flag and original HTTP status. Checks bind the revision delta and 201/200 status to the original effect.

The receipt references the original scoped idempotency reservation, not a live Project membership. Reservation retention controls receipt lifetime and supplies the original expiry, method, concrete route and request fingerprint. Deleting that parent cascades only its receipt. Project/principal scope references restrict unrelated deletion. A downgrade refuses retained receipts and never reverses membership changes.

The [result reader](../../../../apps/backend/src/inframeld_backend/access/infrastructure/readers/postgres_project_membership_change_result_reader.py) requires the exact completed, replayable, unexpired parent binding and coherent receipt. Generic completed-operation metadata alone cannot replace a missing business result. Current authority is checked before this read. Replaying an old add or removal cannot reapply its effects after a later departure or rejoin.

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

## Group administration and deletion recovery

Creation saves the exact scoped Name, creator membership and human management, Project revision, audit and original result together. It adds no document-action grant. Appointment includes ordinary membership, demotion retains it, and member removal clears management first. Rejoining restores no management. A changed request advances the Project Access revision once, while an authorized no-op retains the reviewed revision and its original result.

Current management is checked before ordinary relationship or deletion history. Fresh additions also check current Project membership and recipient eligibility. A suspended human or an application cannot satisfy the last-manager guard. The original relationship result survives later departures and never reapplies an old change.

Unused-group deletion physically removes the current Access relationships and group, retires its Name, and records audit, original result and authentic synchronous status in one transaction. Existing restrictive foreign keys protect the order and scope. Later Document/source/upload/default/case owners add their own restrictive references before their integration is delivered. The default-reference journey remains with #227.

After deletion, current management cannot be proved from a nonexistent group. The original initiator uses the [closed retained recovery path](../../inframeld-application-contracts/references/operation-recovery-contracts.md#access-group-deletion-recovery). This supplies no replacement membership or full group receipt. [Human acceptance #354](https://github.com/matejpalenik/inframeld/issues/354) tracks actual human exercise separately from automated qualification.
