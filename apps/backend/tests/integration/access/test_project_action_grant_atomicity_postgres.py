"""Retain authority, original outcomes and atomic effects through competing turns."""

import asyncio
import os
from typing import Never
from unittest.mock import patch

import pytest
from sqlalchemy import Integer, String, column, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from tests.support.project_action_grant_postgres_scenarios import (
    change_project_grant,
    seed_project_grant_recipients,
)

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_grant_change_result_dto import (
    ProjectActionGrantChangeResultDTO,
)
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.infrastructure.readers.postgres_project_grant_change_facts_reader import (
    PostgresProjectGrantChangeFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_operation_result_row import (
    ProjectActionGrantOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    StaleRevisionError,
)
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


async def _wait_for_grant_lock(
    database: Database, task: asyncio.Task[ProjectActionGrantChangeResultDTO], holder_pid: int
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
    pytest.fail("The grant change bypassed the coordinated Access turn.")


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
async def test_management_facts_reject_snapshot_isolation_before_observing_decisions(
    database: Database, isolation: str
) -> None:
    seed = await seed_project_grant_recipients(database)
    async with database.session() as session, session.begin():
        await session.connection(execution_options={"isolation_level": isolation})
        with pytest.raises(RuntimeError, match="READ COMMITTED"):
            await PostgresProjectGrantChangeFactsReader(session).read_for_management(
                access=seed.actor.access,
                project_id=seed.project.project_id,
                recipient_principal_id=seed.bob_id,
                action_id=ActionId("inspect-budget"),
            )


@pytest.mark.parametrize(
    "failure",
    [RuntimeError("Controlled original-result failure"), asyncio.CancelledError()],
    ids=["error", "cancellation"],
)
async def test_completed_reservation_failure_rolls_back_assignment_revision_and_audit(
    database: Database, failure: BaseException
) -> None:
    seed = await seed_project_grant_recipients(database)
    original = IdempotencyService.record_completed_result

    async def fail_completion(
        self: IdempotencyService,
        operation: NewOperationReservationDTO,
        *,
        replay_kind: OperationReplayKind,
    ) -> Never:
        await original(self, operation, replay_kind=replay_kind)
        raise failure

    with (
        patch.object(IdempotencyService, "record_completed_result", fail_completion),
        pytest.raises(
            type(failure),
            match="Controlled original-result failure"
            if isinstance(failure, RuntimeError)
            else None,
        ),
    ):
        await change_project_grant(database, seed, revision=2, key="failed-completion")
    async with database.session() as session:
        assert (
            await session.get(
                ProjectActionGrantRow,
                (seed.project.project_id.value, seed.bob_id.value, "inspect-budget"),
            )
            is None
        )
        assert await session.scalar(select(ProjectRow.access_revision)) == 2
        assert (
            await session.scalar(
                select(func.count()).select_from(ProjectActionGrantOperationResultRow)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.requested_route.contains("/grants/"))
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(
                    AccessAuditEventRow.affected_principal_id == seed.bob_id.value,
                    AccessAuditEventRow.action == "inspect-budget",
                )
            )
            == 0
        )
    assert (
        await change_project_grant(database, seed, revision=2, key="failed-completion")
    ).status_code == 201


@pytest.mark.parametrize("cancel", [False, True], ids=["fresh-state", "cancel-waiter"])
async def test_organization_wait_rechecks_recipient_and_cancellation_leaves_no_reservation(
    database: Database, cancel: bool
) -> None:
    seed = await seed_project_grant_recipients(database)
    task: asyncio.Task[ProjectActionGrantChangeResultDTO] | None = None
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
                change_project_grant(database, seed, revision=2, key="waiting-grant")
            )
            await _wait_for_grant_lock(database, task, holder_pid)
            if cancel:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                await holder.execute(
                    update(PrincipalRow)
                    .where(PrincipalRow.id == seed.bob_id.value)
                    .values(status=PrincipalStatus.SUSPENDED)
                )
        if not cancel:
            with pytest.raises(ConflictError):
                await task
    finally:
        if task is not None:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    async with database.session() as session:
        assert await session.scalar(select(ProjectRow.access_revision)) == 2
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.requested_route.contains("/grants/"))
            )
            == 0
        )


async def test_concurrent_delegators_cannot_both_remove_their_responsibility(
    database: Database,
) -> None:
    seed = await seed_project_grant_recipients(database)
    await change_project_grant(database, seed, revision=2, key="handover", can_grant=True)
    alice, bob = await asyncio.gather(
        change_project_grant(
            database,
            seed,
            revision=3,
            key="alice-leaves",
            removing=True,
            recipient=seed.actor.access.actor_principal_id,
        ),
        change_project_grant(
            database,
            seed,
            revision=3,
            key="bob-leaves",
            removing=True,
            recipient=seed.bob_id,
            access=AccessContextDTO(seed.bob_id, seed.actor.access.authentication_evidence),
        ),
        return_exceptions=True,
    )
    outcomes = (alice, bob)
    assert sum(isinstance(value, ProjectActionGrantChangeResultDTO) for value in outcomes) == 1
    assert sum(isinstance(value, (StaleRevisionError, ConflictError)) for value in outcomes) == 1
    async with database.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectActionGrantRow)
                .where(
                    ProjectActionGrantRow.project_id == seed.project.project_id.value,
                    ProjectActionGrantRow.action == "inspect-budget",
                    ProjectActionGrantRow.can_grant.is_(True),
                )
            )
            == 1
        )
        assert await session.scalar(select(ProjectRow.access_revision)) == 4
