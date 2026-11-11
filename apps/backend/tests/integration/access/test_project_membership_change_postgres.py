"""Qualify real membership effects, original receipts and serialized safe departures."""

import asyncio
import os
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, update
from tests.support.project_creation_scenarios import create_project
from tests.support.project_membership_postgres_scenarios import (
    MembershipProjectSeedDTO,
    change_membership,
    seed_membership_project,
)

from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_operation_result_row import (
    ProjectMembershipOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_error import ApplicationError
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    StaleRevisionError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]


async def _membership_audits(database: Database) -> int:
    async with database.session() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(
                    AccessAuditEventRow.event_type.in_(
                        (
                            "project_member_added",
                            "project_member_removed",
                            "project_membership_unchanged",
                        )
                    )
                )
            )
            or 0
        )


async def _relationships(database: Database, seed: MembershipProjectSeedDTO) -> tuple[UUID, UUID]:
    """Arrange accepted existing relationships, without claiming public #225/#226 producers."""
    group, application = uuid4(), uuid4()
    project, org = seed.project.project_id.value, seed.actor.organization_id.value
    alice, bob = seed.actor.access.actor_principal_id.value, seed.bob_id.value
    async with database.session() as session, session.begin():
        session.add(
            PrincipalRow(
                id=application,
                organization_id=org,
                kind=PrincipalKind.APPLICATION,
                status=PrincipalStatus.ACTIVE,
                display_name="SupportBot",
            )
        )
        session.add(AccessGroupRow(id=group, project_id=project, name="SupportKnowledge"))
        await session.flush()
        session.add(
            ApplicationAccountRow(
                principal_id=application,
                organization_id=org,
                project_id=project,
                principal_kind=PrincipalKind.APPLICATION,
            )
        )
        await session.flush()
        session.add(
            ProjectMembershipRow(
                project_id=project,
                principal_id=application,
                organization_id=org,
                principal_kind=PrincipalKind.APPLICATION,
                application_principal_id=application,
            )
        )
        for principal in (alice, bob):
            session.add(
                GroupMembershipRow(project_id=project, group_id=group, principal_id=principal)
            )
        await session.flush()
        for principal in (alice, bob):
            session.add(
                GroupManagerRow(
                    project_id=project,
                    group_id=group,
                    principal_id=principal,
                    principal_kind=PrincipalKind.HUMAN,
                )
            )
            session.add(
                ApplicationActionGrantRow(
                    project_id=project,
                    application_principal_id=application,
                    recipient_principal_id=principal,
                    recipient_kind=PrincipalKind.HUMAN,
                    action="issue-application-keys",
                    can_grant=True,
                    assigned_by_principal_id=bob,
                )
            )
        session.add(
            ProjectActionGrantRow(
                project_id=project,
                recipient_principal_id=bob,
                recipient_kind=PrincipalKind.HUMAN,
                action="create-access-groups",
                can_grant=True,
                assigned_by_principal_id=alice,
            )
        )
        session.add(
            GroupActionGrantRow(
                project_id=project,
                group_id=group,
                recipient_principal_id=bob,
                recipient_kind=PrincipalKind.HUMAN,
                action="update-documents",
                can_grant=True,
                assigned_by_principal_id=alice,
            )
        )
        session.add(
            GroupActionGrantRow(
                project_id=project,
                group_id=group,
                recipient_principal_id=alice,
                recipient_kind=PrincipalKind.HUMAN,
                action="add-documents",
                can_grant=False,
                assigned_by_principal_id=bob,
            )
        )
        await session.execute(
            update(ProjectActionGrantRow)
            .where(
                ProjectActionGrantRow.project_id == project,
                ProjectActionGrantRow.recipient_principal_id == alice,
                ProjectActionGrantRow.action == "inspect-budget",
            )
            .values(assigned_by_principal_id=bob)
        )
    return group, application


async def test_add_is_bare_and_no_op_has_its_own_original_status(database: Database) -> None:
    seed = await seed_membership_project(database)
    added = await change_membership(database, seed, revision=1, key="add-bob")
    unchanged = await change_membership(database, seed, revision=2, key="already-bob")
    assert (added.status_code, added.changed, added.access_revision) == (201, True, 2)
    assert (unchanged.status_code, unchanged.changed, unchanged.access_revision) == (200, False, 2)
    async with database.session() as session:
        member = await session.get(
            ProjectMembershipRow, (seed.project.project_id.value, seed.bob_id.value)
        )
        assert (
            member is not None
            and member.assigned_by_principal_id == seed.actor.access.actor_principal_id.value
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectActionGrantRow)
                .where(ProjectActionGrantRow.recipient_principal_id == seed.bob_id.value)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(GroupMembershipRow)
                .where(GroupMembershipRow.principal_id == seed.bob_id.value)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(ProjectMembershipOperationResultRow)
            )
            == 2
        )
    assert await _membership_audits(database) == 2


async def test_remove_clears_only_received_relationships_and_keeps_other_project_and_shared_resources(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    other = await create_project(database, seed.actor, name="test", key="create-test")
    await change_membership(database, seed, revision=1, key="join-support")
    await change_membership(
        database, seed, project_id=other.project.project_id, revision=1, key="join-test"
    )
    group, application = await _relationships(database, seed)
    removed = await change_membership(database, seed, revision=2, key="leave-support", remove=True)
    assert removed.changed and removed.status_code == 200 and removed.access_revision == 3
    project, bob = seed.project.project_id.value, seed.bob_id.value
    async with database.session() as session:
        assert await session.get(ProjectMembershipRow, (project, bob)) is None
        assert (
            await session.get(ProjectMembershipRow, (other.project.project_id.value, bob))
            is not None
        )
        assert await session.get(PrincipalRow, bob) is not None
        assert await session.get(AccessGroupRow, group) is not None
        assert await session.get(ApplicationAccountRow, application) is not None
        assert await session.get(ProjectMembershipRow, (project, application)) is not None
        assert (
            await session.get(
                GroupManagerRow, (project, group, seed.actor.access.actor_principal_id.value)
            )
            is not None
        )
        for row, recipient in (
            (ProjectActionGrantRow, ProjectActionGrantRow.recipient_principal_id),
            (GroupActionGrantRow, GroupActionGrantRow.recipient_principal_id),
            (ApplicationActionGrantRow, ApplicationActionGrantRow.recipient_principal_id),
            (GroupManagerRow, GroupManagerRow.principal_id),
            (GroupMembershipRow, GroupMembershipRow.principal_id),
        ):
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(row)
                    .where(row.project_id == project, recipient == bob)
                )
                == 0
            )
        retained = await session.get(
            ApplicationActionGrantRow,
            (
                project,
                application,
                seed.actor.access.actor_principal_id.value,
                "issue-application-keys",
            ),
        )
        assert (
            retained is not None and retained.assigned_by_principal_id == bob and retained.can_grant
        )
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(
                    ProjectRow.id == other.project.project_id.value
                )
            )
            == 2
        )
    await change_membership(database, seed, revision=3, key="rejoin-support")
    async with database.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectActionGrantRow)
                .where(
                    ProjectActionGrantRow.project_id == project,
                    ProjectActionGrantRow.recipient_principal_id == bob,
                )
            )
            == 0
        )
        assert await session.get(GroupMembershipRow, (project, group, bob)) is None


async def test_replay_survives_removal_and_rejoin_without_reapplying_original_effect(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    added = await change_membership(database, seed, revision=1, key="join")
    removed = await change_membership(database, seed, revision=2, key="leave", remove=True)
    replay_add = await change_membership(database, seed, revision=1, key="join")
    assert replace(replay_add, operation=added.operation) == added
    async with database.session() as session:
        assert (
            await session.get(
                ProjectMembershipRow, (seed.project.project_id.value, seed.bob_id.value)
            )
            is None
        )
    await change_membership(database, seed, revision=3, key="rejoin")
    replay_remove = await change_membership(database, seed, revision=2, key="leave", remove=True)
    assert replace(replay_remove, operation=removed.operation) == removed
    async with database.session() as session:
        assert (
            await session.get(
                ProjectMembershipRow, (seed.project.project_id.value, seed.bob_id.value)
            )
            is not None
        )
        assert await session.scalar(select(ProjectRow.access_revision)) == 4
    assert await _membership_audits(database) == 3


async def test_stale_review_and_lost_authority_leave_no_partial_receipt_or_relationship(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    await change_membership(database, seed, revision=1, key="join")
    with pytest.raises(StaleRevisionError):
        await change_membership(database, seed, revision=1, key="stale", remove=True)
    async with database.session() as session, session.begin():
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == seed.project.project_id.value,
                ProjectActionGrantRow.recipient_principal_id
                == seed.actor.access.actor_principal_id.value,
                ProjectActionGrantRow.action == "manage-project-members",
            )
        )
    with pytest.raises(AccessDeniedError):
        await change_membership(database, seed, revision=2, key="denied", remove=True)
    async with database.session() as session:
        assert (
            await session.get(
                ProjectMembershipRow, (seed.project.project_id.value, seed.bob_id.value)
            )
            is not None
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(ProjectMembershipOperationResultRow)
            )
            == 1
        )
        assert await session.scalar(select(ProjectRow.access_revision)) == 2


@pytest.mark.parametrize("responsibility", ["project", "group", "application"])
async def test_last_human_responsibility_rejects_departure_atomically(
    database: Database, responsibility: str
) -> None:
    seed = await seed_membership_project(database)
    await change_membership(database, seed, revision=1, key="join")
    group, application = await _relationships(database, seed)
    async with database.session() as session, session.begin():
        alice = seed.actor.access.actor_principal_id.value
        if responsibility == "project":
            await session.execute(
                delete(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == seed.project.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id == alice,
                    ProjectActionGrantRow.action == "create-access-groups",
                )
            )
        elif responsibility == "group":
            await session.execute(
                delete(GroupManagerRow).where(
                    GroupManagerRow.project_id == seed.project.project_id.value,
                    GroupManagerRow.group_id == group,
                    GroupManagerRow.principal_id == alice,
                )
            )
        else:
            await session.execute(
                delete(ApplicationActionGrantRow).where(
                    ApplicationActionGrantRow.project_id == seed.project.project_id.value,
                    ApplicationActionGrantRow.application_principal_id == application,
                    ApplicationActionGrantRow.recipient_principal_id == alice,
                )
            )
    with pytest.raises(ConflictError):
        await change_membership(database, seed, revision=2, key="stranded", remove=True)
    async with database.session() as session:
        assert (
            await session.get(
                ProjectMembershipRow, (seed.project.project_id.value, seed.bob_id.value)
            )
            is not None
        )
        assert (
            await session.get(
                GroupManagerRow, (seed.project.project_id.value, group, seed.bob_id.value)
            )
            is not None
        )
        assert await session.scalar(select(ProjectRow.access_revision)) == 2
        assert (
            await session.scalar(
                select(func.count()).select_from(ProjectMembershipOperationResultRow)
            )
            == 1
        )


async def test_two_concurrent_departures_cannot_each_rely_on_the_other_remaining(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    await change_membership(database, seed, revision=1, key="join")
    async with database.session() as session, session.begin():
        actions = (
            await session.scalars(
                select(ProjectActionGrantRow.action).where(
                    ProjectActionGrantRow.project_id == seed.project.project_id.value
                )
            )
        ).all()
        for action in actions:
            session.add(
                ProjectActionGrantRow(
                    project_id=seed.project.project_id.value,
                    recipient_principal_id=seed.bob_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=action,
                    can_grant=True,
                )
            )
    bob = seed.bob_access
    outcomes = await asyncio.gather(
        change_membership(
            database,
            seed,
            principal_id=seed.actor.access.actor_principal_id,
            revision=2,
            key="alice-leaves",
            remove=True,
        ),
        change_membership(database, seed, revision=2, key="bob-leaves", remove=True, access=bob),
        return_exceptions=True,
    )
    assert sum(isinstance(outcome, ApplicationError) for outcome in outcomes) == 1
    assert sum(not isinstance(outcome, BaseException) for outcome in outcomes) == 1
    async with database.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectMembershipRow)
                .where(ProjectMembershipRow.project_id == seed.project.project_id.value)
            )
            == 1
        )
        assert await session.scalar(select(ProjectRow.access_revision)) == 3
