"""Qualify the real account identity, empty permissions and exact human creator grants."""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import Integer, String, column, delete, event, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from tests.support.application_account_scenarios import (
    account_command,
    account_context,
    create_account,
    creation_service,
)
from tests.support.project_creation_scenarios import create_project, seed_project_creator

from inframeld_backend.access.application.dtos.application_account_creation_result_dto import (
    ApplicationAccountCreationResultDTO,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.application_account_creation_result_row import (
    ApplicationAccountCreationResultRow,
)
from inframeld_backend.access.infrastructure.rows.application_account_name_reservation_row import (
    ApplicationAccountNameReservationRow,
)
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]


async def test_atomic_creation_has_one_identity_empty_account_and_three_human_grants(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    result = await create_account(database, seed.access, project.project_id)
    account = result.account
    assert account.principal_id != seed.access.actor_principal_id
    async with database.session() as session:
        principal = await session.get(PrincipalRow, account.principal_id.value)
        extension = await session.get(ApplicationAccountRow, account.principal_id.value)
        membership = await session.get(
            ProjectMembershipRow, (project.project_id.value, account.principal_id.value)
        )
        assert (
            principal is not None
            and principal.kind is PrincipalKind.APPLICATION
            and principal.display_name == "SupportBot"
        )
        assert (
            extension is not None
            and extension.principal_id == principal.id
            and extension.project_id == project.project_id.value
        )
        assert membership is not None and membership.application_principal_id == principal.id
        assert extension.resource_name == "support-bot"
        assert await session.scalar(select(func.count()).select_from(ApplicationKeyRow)) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectActionGrantRow)
                .where(ProjectActionGrantRow.recipient_principal_id == principal.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(GroupMembershipRow)
                .where(GroupMembershipRow.principal_id == principal.id)
            )
            == 0
        )
        grants = (
            await session.scalars(
                select(ApplicationActionGrantRow).where(
                    ApplicationActionGrantRow.application_principal_id == principal.id
                )
            )
        ).all()
        assert {
            (grant.action, grant.recipient_principal_id, grant.can_grant) for grant in grants
        } == {
            (action, seed.access.actor_principal_id.value, True)
            for action in (
                "issue-application-keys",
                "revoke-application-keys",
                "delete-application-account",
            )
        }
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == project.project_id.value)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(
                    AccessAuditEventRow.event_type == "application_account_created",
                    AccessAuditEventRow.correlation_id == result.operation.operation_id.value,
                )
            )
            == 1
        )


async def _assert_account_count(database: Database, expected: int) -> None:
    async with database.session() as session:
        for model in (
            ApplicationAccountRow,
            ApplicationAccountNameReservationRow,
            ApplicationAccountCreationResultRow,
        ):
            assert await session.scalar(select(func.count()).select_from(model)) == expected
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PrincipalRow)
                .where(PrincipalRow.kind == PrincipalKind.APPLICATION)
            )
            == expected
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.lookup_action_id == "create-application-accounts")
            )
            == expected
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "application_account_created")
            )
            == expected
        )


async def test_creation_replay_keeps_original_receipt_without_restoring_removed_grants(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    original = await create_account(database, seed.access, project.project_id)
    async with database.session() as session, session.begin():
        await session.execute(
            delete(ApplicationActionGrantRow).where(
                ApplicationActionGrantRow.application_principal_id
                == original.account.principal_id.value
            )
        )
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == original.account.principal_id.value)
            .values(display_name="Later label")
        )
        await session.execute(
            update(ProjectRow)
            .where(ProjectRow.id == project.project_id.value)
            .values(access_revision=9007199254740991)
        )
    replay = await create_account(database, seed.access, project.project_id)
    assert replay.account == original.account
    assert replay.operation.operation_id == original.operation.operation_id
    assert replay.operation.expires_at == original.operation.expires_at
    assert not replay.operation.created
    await _assert_account_count(database, 1)
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ApplicationActionGrantRow)) == 0
        )
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == project.project_id.value)
            )
            == 9007199254740991
        )


@pytest.mark.parametrize("change", ["grant", "suspension", "membership"])
async def test_current_authority_precedes_existing_or_missing_creation_history(
    database: Database, change: str
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    await create_account(database, seed.access, project.project_id)
    async with database.session() as session, session.begin():
        if change == "grant":
            await session.execute(
                delete(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == project.project_id.value,
                    ProjectActionGrantRow.action == "create-application-accounts",
                )
            )
        elif change == "suspension":
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == seed.access.actor_principal_id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )
        else:
            await session.execute(
                delete(ApplicationActionGrantRow).where(
                    ApplicationActionGrantRow.recipient_principal_id
                    == seed.access.actor_principal_id.value
                )
            )
            await session.execute(
                delete(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == project.project_id.value
                )
            )
            await session.execute(
                delete(ProjectMembershipRow).where(
                    ProjectMembershipRow.project_id == project.project_id.value,
                    ProjectMembershipRow.principal_id == seed.access.actor_principal_id.value,
                )
            )
    for key in ("create-bot", "never-created"):
        with pytest.raises((AccessDeniedError, ResourceNotFoundError)):
            await create_account(database, seed.access, project.project_id, key=key)
    await _assert_account_count(database, 1)


async def test_scoped_name_collision_rolls_back_the_new_principal_and_reservation(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    await create_account(database, seed.access, project.project_id)
    with pytest.raises(ConflictError):
        await create_account(database, seed.access, project.project_id, revision=2, key="collision")
    await _assert_account_count(database, 1)
    async with database.session() as session:
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == project.project_id.value)
            )
            == 2
        )


async def test_concurrent_creation_admits_one_review_and_leaves_no_orphan(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    results = await asyncio.gather(
        *(
            create_account(database, seed.access, project.project_id, key=f"race-{index}")
            for index in range(2)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, ApplicationAccountCreationResultDTO) for result in results) == 1
    assert sum(isinstance(result, StaleRevisionError) for result in results) == 1
    await _assert_account_count(database, 1)


async def test_concurrent_same_request_recovers_one_original_identity(database: Database) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    first, second = await asyncio.gather(
        create_account(database, seed.access, project.project_id),
        create_account(database, seed.access, project.project_id),
    )
    assert first.account == second.account
    assert first.operation.operation_id == second.operation.operation_id
    await _assert_account_count(database, 1)
    async with database.session() as session:
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == project.project_id.value)
            )
            == 2
        )
        assert (
            await session.scalar(select(func.count()).select_from(ApplicationActionGrantRow)) == 3
        )


async def test_same_name_in_two_projects_has_distinct_stable_identities(database: Database) -> None:
    seed = await seed_project_creator(database)
    first = (await create_project(database, seed)).project
    second = (await create_project(database, seed, name="other", key="other-project")).project
    one = await create_account(database, seed.access, first.project_id, key="one")
    two = await create_account(database, seed.access, second.project_id, key="two")
    assert one.account.principal_id != two.account.principal_id
    assert one.account.name == two.account.name
    await _assert_account_count(database, 2)


@pytest.mark.parametrize("failure", ["audit", "commit"])
async def test_failed_required_audit_or_commit_rolls_back_all_creation_effects(
    database: Database, failure: str
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    async with database.session() as session:

        def fail_audit(_session: Session, _context: object, _instances: object) -> None:
            if any(
                isinstance(row, AccessAuditEventRow)
                and row.event_type == "application_account_created"
                for row in _session.new
            ):
                raise RuntimeError("Controlled required audit failure")

        def fail_commit(_session: Session) -> None:
            raise RuntimeError("Controlled commit failure")

        hook = "before_flush" if failure == "audit" else "before_commit"
        callback = fail_audit if failure == "audit" else fail_commit
        event.listen(session.sync_session, hook, callback)
        try:
            with pytest.raises(RuntimeError, match="Controlled"):
                await creation_service(session).create(
                    access=seed.access,
                    command=account_command(project.project_id),
                    context=account_context(project.project_id),
                )
        finally:
            event.remove(session.sync_session, hook, callback)
    await _assert_account_count(database, 0)
    async with database.session() as session:
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == project.project_id.value)
            )
            == 1
        )


async def test_hidden_project_and_exhausted_revision_create_nothing(database: Database) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    with pytest.raises(ResourceNotFoundError):
        await create_account(database, seed.access, ProjectId(uuid4()))
    async with database.session() as session, session.begin():
        await session.execute(
            update(ProjectRow)
            .where(ProjectRow.id == project.project_id.value)
            .values(access_revision=9007199254740991)
        )
    with pytest.raises(ConflictError):
        await create_account(database, seed.access, project.project_id, revision=9007199254740991)
    await _assert_account_count(database, 0)


async def test_retired_name_or_reused_display_name_cannot_revive_old_identity(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    old = await create_account(database, seed.access, project.project_id)
    async with database.session() as session, session.begin():
        await session.execute(
            delete(ApplicationActionGrantRow).where(
                ApplicationActionGrantRow.application_principal_id == old.account.principal_id.value
            )
        )
        await session.execute(
            delete(ProjectMembershipRow).where(
                ProjectMembershipRow.principal_id == old.account.principal_id.value
            )
        )
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == old.account.principal_id.value)
            .values(status=PrincipalStatus.RETIRED)
        )
        await session.execute(
            update(ApplicationAccountNameReservationRow)
            .where(
                ApplicationAccountNameReservationRow.application_principal_id
                == old.account.principal_id.value
            )
            .values(retired=True)
        )
        await session.execute(
            update(ApplicationAccountRow)
            .where(ApplicationAccountRow.principal_id == old.account.principal_id.value)
            .values(resource_name=None)
        )
    with pytest.raises(ConflictError):
        await create_account(
            database, seed.access, project.project_id, revision=2, key="reuse-name"
        )
    replacement = await create_account(
        database, seed.access, project.project_id, revision=2, name="replacement", key="replacement"
    )
    assert replacement.account.principal_id != old.account.principal_id
    assert replacement.account.display_name == old.account.display_name
    async with database.session() as session:
        assert (
            await session.scalar(
                select(PrincipalRow.status).where(PrincipalRow.id == old.account.principal_id.value)
            )
            is PrincipalStatus.RETIRED
        )
    await _assert_account_count(database, 2)


@pytest.mark.parametrize("change", ["clear-existing", "cross-project"])
async def test_application_membership_requires_non_null_matching_account_binding(
    database: Database, change: str
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    other = (await create_project(database, seed, name="other", key="other-project")).project
    account = (await create_account(database, seed.access, project.project_id)).account
    async with database.session() as session:
        human = await session.get(
            ProjectMembershipRow, (project.project_id.value, seed.access.actor_principal_id.value)
        )
        member = await session.get(
            ProjectMembershipRow, (project.project_id.value, account.principal_id.value)
        )
        assert human is not None and human.application_principal_id is None
        assert member is not None and member.application_principal_id == account.principal_id.value
    with pytest.raises(IntegrityError):
        async with database.session() as session, session.begin():
            if change == "clear-existing":
                await session.execute(
                    update(ProjectMembershipRow)
                    .where(
                        ProjectMembershipRow.project_id == project.project_id.value,
                        ProjectMembershipRow.principal_id == account.principal_id.value,
                    )
                    .values(application_principal_id=None)
                )
            else:
                session.add(
                    ProjectMembershipRow(
                        project_id=other.project_id.value,
                        principal_id=account.principal_id.value,
                        organization_id=seed.organization_id.value,
                        principal_kind=PrincipalKind.APPLICATION,
                        application_principal_id=None,
                    )
                )
            await session.flush()
    async with database.session() as session:
        member = await session.get(
            ProjectMembershipRow, (project.project_id.value, account.principal_id.value)
        )
        assert member is not None and member.application_principal_id == account.principal_id.value
        assert (
            await session.get(
                ProjectMembershipRow, (other.project_id.value, account.principal_id.value)
            )
            is None
        )


async def test_application_extension_and_membership_reject_wrong_kind_or_project(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    first = (await create_project(database, seed)).project
    second = (await create_project(database, seed, name="other", key="other-project")).project
    account = (await create_account(database, seed.access, first.project_id)).account
    async with database.session() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                session.add(
                    ApplicationAccountRow(
                        principal_id=seed.access.actor_principal_id.value,
                        organization_id=seed.organization_id.value,
                        project_id=first.project_id.value,
                        principal_kind=PrincipalKind.APPLICATION,
                    )
                )
                await session.flush()
    async with database.session() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                session.add(
                    ProjectMembershipRow(
                        project_id=second.project_id.value,
                        principal_id=account.principal_id.value,
                        organization_id=seed.organization_id.value,
                        principal_kind=PrincipalKind.APPLICATION,
                        application_principal_id=account.principal_id.value,
                    )
                )
                await session.flush()
    async with database.session() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                await session.execute(
                    update(ApplicationAccountRow)
                    .where(ApplicationAccountRow.principal_id == account.principal_id.value)
                    .values(project_id=second.project_id.value)
                )
    async with database.session() as session:
        assert (
            await session.scalar(
                select(ApplicationAccountRow.project_id).where(
                    ApplicationAccountRow.principal_id == account.principal_id.value
                )
            )
            == first.project_id.value
        )


async def test_creation_crosses_int32_and_preserves_maximum_original_replay(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    async with database.session() as session, session.begin():
        await session.execute(
            update(ProjectRow)
            .where(ProjectRow.id == project.project_id.value)
            .values(access_revision=2**31 - 1)
        )
    wide = await create_account(
        database, seed.access, project.project_id, revision=2**31 - 1, key="wide"
    )
    assert wide.account.access_revision == 2**31
    async with database.session() as session, session.begin():
        await session.execute(
            update(ProjectRow)
            .where(ProjectRow.id == project.project_id.value)
            .values(access_revision=9007199254740990)
        )
    final = await create_account(
        database,
        seed.access,
        project.project_id,
        revision=9007199254740990,
        name="final",
        key="final",
    )
    assert final.account.access_revision == 9007199254740991
    replay = await create_account(
        database, seed.access, project.project_id, revision=2**31 - 1, key="wide"
    )
    assert replay.account == wide.account and not replay.operation.created
    await _assert_account_count(database, 2)


@pytest.mark.parametrize("turn", ["organization", "project"])
async def test_authority_is_reread_after_real_coordination_wait(
    database: Database, turn: str
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    pending: asyncio.Task[ApplicationAccountCreationResultDTO] | None = None
    try:
        async with database.session() as gate, gate.begin():
            if turn == "organization":
                await gate.scalar(
                    select(OrganizationRow.id)
                    .where(OrganizationRow.id == seed.organization_id.value)
                    .with_for_update()
                )
            else:
                await gate.scalar(
                    select(ProjectRow.id)
                    .where(ProjectRow.id == project.project_id.value)
                    .with_for_update()
                )
            pending = asyncio.create_task(create_account(database, seed.access, project.project_id))
            # Observe a real PostgreSQL wait before changing the state whose
            # current value must be checked after the coordination turn.
            pid, name = column("pid", Integer), column("datname", String)
            activity = table("pg_stat_activity", pid, name)
            blocked = None
            async with asyncio.timeout(3):
                while blocked is None and not pending.done():
                    async with database.session() as connection:
                        blocked = await connection.scalar(
                            select(pid)
                            .select_from(activity)
                            .where(
                                name == func.current_database(type_=String()),
                                func.cardinality(
                                    func.pg_blocking_pids(pid, type_=ARRAY(Integer)), type_=Integer
                                )
                                > 0,
                            )
                        )
                    if blocked is None:
                        await asyncio.sleep(0.01)
            assert blocked is not None and not pending.done()
            if turn == "organization":
                await gate.execute(
                    update(PrincipalRow)
                    .where(PrincipalRow.id == seed.access.actor_principal_id.value)
                    .values(status=PrincipalStatus.SUSPENDED)
                )
            else:
                await gate.execute(
                    delete(ProjectActionGrantRow).where(
                        ProjectActionGrantRow.project_id == project.project_id.value,
                        ProjectActionGrantRow.action == "create-application-accounts",
                    )
                )
        with pytest.raises((AccessDeniedError, ResourceNotFoundError)):
            await pending
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
    await _assert_account_count(database, 0)
