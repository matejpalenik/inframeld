"""Verify durable reservation identity against PostgreSQL."""

import asyncio
import os
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update
from tests.support.access_scenarios import MockAccessScenarios

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_result_dto import (
    OperationReservationResultDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    IdempotencyKeyReusedError,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


async def _request(database: Database) -> OperationReservationRequestDTO:
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
        )
        organization_id = await session.scalar(
            select(ProjectRow.organization_id).where(ProjectRow.id == scenario.project_id.value)
        )
        assert organization_id is not None

    return OperationReservationRequestDTO(
        principal_id=scenario.principal_id,
        organization_id=OrganizationId(organization_id),
        project_id=scenario.project_id,
        method="POST",
        requested_route="/v1/projects/{project_id}/builds",
        key=IdempotencyKey("build-request-1"),
        fingerprint=b"\x01" * 32,
    )


async def _reserve(
    database: Database,
    request: OperationReservationRequestDTO,
) -> OperationReservationResultDTO:
    async with database.session() as session, session.begin():
        return await PostgresOperationReservationWriter(session).reserve(request)


@pytest.mark.asyncio
@pytest.mark.parametrize("organization_level", [False, True])
async def test_concurrent_equal_requests_share_one_operation(
    database: Database,
    organization_level: bool,
) -> None:
    request = await _request(database)
    if organization_level:
        request = replace(
            request,
            project_id=None,
            requested_route="/v1/organization/operations",
        )

    barrier = asyncio.Barrier(2)

    async def admit() -> OperationReservationResultDTO:
        async with database.session() as session, session.begin():
            await barrier.wait()
            return await PostgresOperationReservationWriter(session).reserve(request)

    first, second = await asyncio.gather(admit(), admit())

    assert first.operation_id == second.operation_id
    assert sorted((first.created, second.created)) == [False, True]

    async with database.session() as session:
        count = await session.scalar(select(func.count()).select_from(IdempotencyReservationRow))
    assert count == 1


@pytest.mark.asyncio
async def test_changed_input_under_one_key_conflicts(database: Database) -> None:
    request = await _request(database)
    await _reserve(database, request)

    with pytest.raises(IdempotencyKeyReusedError):
        await _reserve(database, replace(request, fingerprint=b"\x02" * 32))


@pytest.mark.asyncio
async def test_writer_does_not_commit_the_callers_transaction(database: Database) -> None:
    request = await _request(database)

    class AbortForTest(Exception):
        pass

    with pytest.raises(AbortForTest):
        async with database.session() as session, session.begin():
            await PostgresOperationReservationWriter(session).reserve(request)
            raise AbortForTest

    result = await _reserve(database, request)
    assert result.created


@pytest.mark.asyncio
async def test_completed_safe_result_starts_24_hour_retention(database: Database) -> None:
    """Start expiry when a safe synchronous outcome is recorded."""
    request = await _request(database)

    async with database.session() as session, session.begin():
        writer = PostgresOperationReservationWriter(session)
        reservation = await writer.reserve(request)
        before_completion = await session.scalar(select(func.clock_timestamp()))
        assert before_completion is not None

        await writer.mark_replayable(
            reservation.operation_id,
            OperationReplayKind.SAFE_RESULT,
        )

        expires_at = await session.scalar(
            select(IdempotencyReservationRow.expires_at).where(
                IdempotencyReservationRow.operation_id == reservation.operation_id.value
            )
        )

    assert expires_at is not None
    assert expires_at >= before_completion + timedelta(hours=24)


@pytest.mark.asyncio
async def test_expired_completed_scope_is_replaced_once_under_concurrency(
    database: Database,
) -> None:
    """After retention, concurrent requests still establish only one new operation."""
    request = await _request(database)

    async with database.session() as session, session.begin():
        writer = PostgresOperationReservationWriter(session)
        original = await writer.reserve(request)
        await writer.mark_replayable(original.operation_id, OperationReplayKind.SAFE_RESULT)
        await session.execute(
            update(IdempotencyReservationRow)
            .where(IdempotencyReservationRow.operation_id == original.operation_id.value)
            .values(expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )

    changed_request = replace(request, fingerprint=b"\x02" * 32)
    barrier = asyncio.Barrier(2)

    async def retry() -> OperationReservationResultDTO:
        async with database.session() as session, session.begin():
            await barrier.wait()
            return await PostgresOperationReservationWriter(session).reserve(changed_request)

    first, second = await asyncio.gather(retry(), retry())

    assert first.operation_id == second.operation_id
    assert first.operation_id != original.operation_id
    assert sorted((first.created, second.created)) == [False, True]

    async with database.session() as session:
        count = await session.scalar(select(func.count()).select_from(IdempotencyReservationRow))
    assert count == 1


@pytest.mark.asyncio
async def test_async_acceptance_is_recorded_for_replay(database: Database) -> None:
    request = await _request(database)

    async with database.session() as session, session.begin():
        writer = PostgresOperationReservationWriter(session)
        reservation = await writer.reserve(request)
        await writer.mark_replayable(
            reservation.operation_id,
            OperationReplayKind.ASYNC_JOB,
        )

    async with database.session() as session:
        row = await session.scalar(
            select(IdempotencyReservationRow).where(
                IdempotencyReservationRow.operation_id == reservation.operation_id.value
            )
        )

    assert row is not None
    assert row.state is OperationReservationState.REPLAYABLE
    assert row.replay_kind is OperationReplayKind.ASYNC_JOB


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", list(OperationReplayKind))
async def test_equal_retry_returns_recorded_replay_decision(
    database: Database,
    kind: OperationReplayKind,
) -> None:
    request = await _request(database)

    async with database.session() as session, session.begin():
        writer = PostgresOperationReservationWriter(session)
        first = await writer.reserve(request)
        await writer.mark_replayable(first.operation_id, kind)

    retry = await _reserve(database, request)

    assert not retry.created
    assert retry.operation_id == first.operation_id
    assert retry.state is OperationReservationState.REPLAYABLE
    assert retry.replay_kind is kind


@pytest.mark.asyncio
async def test_uncertain_retry_keeps_original_operation(database: Database) -> None:
    request = replace(
        await _request(database),
        requested_route="/v1/projects/{project_id}/provider-query",
    )

    async with database.session() as session, session.begin():
        writer = PostgresOperationReservationWriter(session)
        first = await writer.reserve(request)
        await writer.mark_recovery_required(first.operation_id)

    retry = await _reserve(database, request)

    assert not retry.created
    assert retry.operation_id == first.operation_id
    assert retry.state is OperationReservationState.RECOVERY_REQUIRED
    assert retry.replay_kind is None


@pytest.mark.asyncio
async def test_accepted_async_reservation_keeps_its_replay_kind(
    database: Database,
) -> None:
    request = await _request(database)

    async with database.session() as session, session.begin():
        writer = PostgresOperationReservationWriter(session)
        first = await writer.reserve(request)
        await writer.mark_replayable(first.operation_id, OperationReplayKind.ASYNC_JOB)

        with pytest.raises(ConflictError):
            await writer.mark_recovery_required(first.operation_id)

    retry = await _reserve(database, request)
    assert retry.state is OperationReservationState.REPLAYABLE
    assert retry.replay_kind is OperationReplayKind.ASYNC_JOB
