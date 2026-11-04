"""Keep effects, audit and business replay together through failure and lock waits."""

import asyncio
import os
from typing import Never
from unittest.mock import patch

import pytest
from sqlalchemy import Integer, String, column, delete, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from tests.support.project_membership_postgres_scenarios import (
    change_membership,
    seed_membership_project,
)

from inframeld_backend.access.application.dtos.project_membership_change_result_dto import (
    ProjectMembershipChangeResultDTO,
)
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.infrastructure.readers.postgres_project_membership_change_facts_reader import (
    PostgresProjectMembershipChangeFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_operation_result_row import (
    ProjectMembershipOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
async def test_snapshot_isolation_cannot_observe_membership_change_facts(
    database: Database, isolation: str
) -> None:
    """Reject snapshots that could retain obsolete authority after a coordination wait."""
    seed = await seed_membership_project(database)
    async with database.session() as session, session.begin():
        await session.connection(execution_options={"isolation_level": isolation})
        with pytest.raises(RuntimeError, match="READ COMMITTED"):
            await PostgresProjectMembershipChangeFactsReader(session).read_for_change(
                access=seed.actor.access,
                project_id=seed.project.project_id,
                principal_id=seed.bob_id,
                removing=False,
            )
    async with database.session() as session:
        assert await session.scalar(select(ProjectRow.access_revision)) == 1
        assert (
            await session.get(
                ProjectMembershipRow, (seed.project.project_id.value, seed.bob_id.value)
            )
            is None
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(ProjectMembershipOperationResultRow)
            )
            == 0
        )


async def _wait_for_lock(
    database: Database, task: asyncio.Task[ProjectMembershipChangeResultDTO], holder_pid: int
) -> None:
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    async with asyncio.timeout(10):
        while not task.done():
            async with database.session() as observer:
                blocked = await observer.scalar(
                    select(pid)
                    .select_from(activity)
                    .where(
                        name == func.current_database(type_=String()),
                        func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains([holder_pid]),
                    )
                )
            if blocked is not None:
                return
            await asyncio.sleep(0.01)
    task.result()
    pytest.fail("Membership change bypassed the required Access turn.")


@pytest.mark.parametrize(
    "failure",
    [RuntimeError("Controlled completion failure"), asyncio.CancelledError()],
    ids=["completion-error", "cancellation"],
)
async def test_failure_after_effects_and_completion_rolls_back_every_local_result(
    database: Database, failure: BaseException
) -> None:
    seed = await seed_membership_project(database)
    original = IdempotencyService.record_completed_result

    async def fail_completed(
        self: IdempotencyService,
        operation: NewOperationReservationDTO,
        *,
        replay_kind: OperationReplayKind,
    ) -> Never:
        await original(self, operation, replay_kind=replay_kind)
        raise failure

    with (
        patch.object(IdempotencyService, "record_completed_result", fail_completed),
        pytest.raises(type(failure)),
    ):
        await change_membership(database, seed, revision=1, key="failed-join")
    async with database.session() as session:
        assert (
            await session.get(
                ProjectMembershipRow, (seed.project.project_id.value, seed.bob_id.value)
            )
            is None
        )
        assert await session.scalar(select(ProjectRow.access_revision)) == 1
        assert (
            await session.scalar(
                select(func.count()).select_from(ProjectMembershipOperationResultRow)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.method == "PUT")
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "project_member_added")
            )
            == 0
        )
    retried = await change_membership(database, seed, revision=1, key="failed-join")
    assert retried.changed and retried.access_revision == 2


async def test_waiting_add_reads_recipient_state_committed_by_preceding_organization_turn(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    task: asyncio.Task[ProjectMembershipChangeResultDTO] | None = None
    try:
        async with database.session() as holder, holder.begin():
            holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
            assert holder_pid is not None
            await holder.scalar(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == seed.actor.organization_id.value)
                .with_for_update()
            )
            task = asyncio.create_task(
                change_membership(database, seed, revision=1, key="waiting-join")
            )
            await _wait_for_lock(database, task, holder_pid)
            await holder.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == seed.bob_id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )
        with pytest.raises(ConflictError):
            await task
    finally:
        if task is not None:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    async with database.session() as session:
        assert (
            await session.get(
                ProjectMembershipRow, (seed.project.project_id.value, seed.bob_id.value)
            )
            is None
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(ProjectMembershipOperationResultRow)
            )
            == 0
        )
        assert await session.scalar(select(ProjectRow.access_revision)) == 1


async def test_actual_cancellation_while_waiting_releases_transaction_without_a_reservation(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    task: asyncio.Task[ProjectMembershipChangeResultDTO] | None = None
    try:
        async with database.session() as holder, holder.begin():
            holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
            assert holder_pid is not None
            await holder.scalar(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == seed.actor.organization_id.value)
                .with_for_update()
            )
            task = asyncio.create_task(
                change_membership(database, seed, revision=1, key="cancelled-join")
            )
            await _wait_for_lock(database, task, holder_pid)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    finally:
        if task is not None:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    async with database.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.method == "PUT")
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(ProjectMembershipOperationResultRow)
            )
            == 0
        )
    assert (await change_membership(database, seed, revision=1, key="cancelled-join")).changed


async def test_generic_completed_metadata_cannot_replace_missing_original_business_receipt(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    added = await change_membership(database, seed, revision=1, key="join")
    await change_membership(database, seed, revision=2, key="leave", remove=True)
    async with database.session() as session, session.begin():
        await session.execute(
            delete(ProjectMembershipOperationResultRow).where(
                ProjectMembershipOperationResultRow.operation_id
                == added.operation.operation_id.value
            )
        )
    with pytest.raises(ConflictError):
        await change_membership(database, seed, revision=1, key="join")
    async with database.session() as session:
        assert (
            await session.get(
                ProjectMembershipRow, (seed.project.project_id.value, seed.bob_id.value)
            )
            is None
        )
        assert await session.scalar(select(ProjectRow.access_revision)) == 3


@pytest.mark.parametrize("remove", [False, True], ids=["no-op-add", "no-op-remove"])
async def test_original_no_change_receipt_does_not_reapply_after_opposite_later_change(
    database: Database, remove: bool
) -> None:
    seed = await seed_membership_project(database)
    if not remove:
        await change_membership(database, seed, revision=1, key="first-join")
    revision = 1 if remove else 2
    original = await change_membership(
        database, seed, revision=revision, key="no-op", remove=remove
    )
    assert not original.changed and original.status_code == 200
    await change_membership(database, seed, revision=revision, key="opposite", remove=not remove)
    replay = await change_membership(database, seed, revision=revision, key="no-op", remove=remove)
    assert not replay.changed and replay.access_revision == original.access_revision
    assert (
        replay.status_code == original.status_code
        and replay.operation.expires_at == original.operation.expires_at
    )
    async with database.session() as session:
        assert (
            await session.get(
                ProjectMembershipRow, (seed.project.project_id.value, seed.bob_id.value)
            )
            is not None
        ) is remove
        assert await session.scalar(select(ProjectRow.access_revision)) == revision + 1
