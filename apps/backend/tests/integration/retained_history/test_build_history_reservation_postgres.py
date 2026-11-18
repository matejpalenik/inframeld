"""Exercise the installation budget using actual operation reservations and PostgreSQL turns."""

import asyncio
import os
from typing import override
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.project_creation_scenarios import create_project, seed_project_creator

from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.pipelines.domain.value_objects.pipeline_id import PipelineId
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.errors.retained_history_errors import (
    RetainedHistoryCapacityError,
)
from inframeld_backend.shared.application.protocols.retained_history_safety_headroom import (
    RetainedHistorySafetyHeadroom,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.retained_history_capacity_row import (
    RetainedHistoryCapacityRow,
)
from inframeld_backend.shared.infrastructure.rows.retained_history_reservation_row import (
    RetainedHistoryReservationRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_build_history_reservation_writer import (
    PostgresBuildHistoryReservationWriter,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1", reason="Requires isolated PostgreSQL"
    ),
]
_CHARGE = 1024**2
_DEFAULT_LIMIT = 10 * 1024**3


class MockRetainedHistorySafetyHeadroom(RetainedHistorySafetyHeadroom):
    def __init__(self, installation_id: InstallationId, *, available: bool = True) -> None:
        self._installation_id = installation_id
        self.available = available
        self.checked = 0

    @override
    async def require_headroom(self, *, installation_id: InstallationId) -> None:
        assert self._installation_id == installation_id
        self.checked += 1
        if not self.available:
            raise DependencyUnavailableError("The retained safety headroom is unavailable.")


class SimulatedAdmissionRollback(Exception):
    pass


async def _original(
    session: AsyncSession,
    scope: ArtifactScopeDTO,
    principal: PrincipalId,
    pipeline_id: PipelineId,
    key: str,
) -> OperationId:
    result = await PostgresOperationReservationWriter(session).reserve(
        OperationReservationRequestDTO(
            principal_id=principal,
            organization_id=scope.organization_id,
            project_id=scope.project_id,
            method=HttpMethod.POST,
            requested_route=(
                f"/internal/projects/{scope.project_id.value}/pipelines/{pipeline_id.value}/builds"
            ),
            key=IdempotencyKey(key),
            fingerprint=b"h" * 32,
        ),
    )
    assert result.created
    return result.operation_id


async def test_exact_build_history_charge_is_atomic_and_reuses_its_original(
    database: Database,
) -> None:
    actor = await seed_project_creator(database)
    project = (await create_project(database, actor)).project.project_id
    scope = ArtifactScopeDTO(actor.binding.installation_id, actor.organization_id, project)
    principal = actor.access.actor_principal_id
    pipeline_id = PipelineId(uuid4())
    safety = MockRetainedHistorySafetyHeadroom(scope.installation_id)

    async with database.session() as session, session.begin():
        capacity = await session.get(RetainedHistoryCapacityRow, 1)
        assert capacity is not None and capacity.ordinary_limit_bytes == _DEFAULT_LIMIT
        assert capacity.reserved_bytes == 0
        operation_id = await _original(session, scope, principal, pipeline_id, "committed")
        writer = PostgresBuildHistoryReservationWriter(session, safety_headroom=safety)
        await writer.reserve_build(scope=scope, operation_id=operation_id, pipeline_id=pipeline_id)
        await writer.reserve_build(scope=scope, operation_id=operation_id, pipeline_id=pipeline_id)
        assert safety.checked == 1
        with pytest.raises(ConflictError):
            await writer.reserve_build(
                scope=scope, operation_id=operation_id, pipeline_id=PipelineId(uuid4())
            )

    rolled_back: OperationId | None = None
    with pytest.raises(SimulatedAdmissionRollback):
        async with database.session() as session, session.begin():
            rolled_back = await _original(session, scope, principal, pipeline_id, "aborted")
            await PostgresBuildHistoryReservationWriter(
                session, safety_headroom=safety
            ).reserve_build(scope=scope, operation_id=rolled_back, pipeline_id=pipeline_id)
            raise SimulatedAdmissionRollback

    assert rolled_back is not None
    async with database.session() as session:
        total = await session.get(RetainedHistoryCapacityRow, 1)
        row = await session.get(RetainedHistoryReservationRow, operation_id.value)
        assert total is not None and total.reserved_bytes == _CHARGE
        assert row is not None and row.reserved_bytes == _CHARGE
        assert (row.installation_id, row.organization_id, row.project_id) == (
            scope.installation_id.value,
            scope.organization_id.value,
            scope.project_id.value,
        )
        assert await session.get(RetainedHistoryReservationRow, rolled_back.value) is None
        assert await session.get(IdempotencyReservationRow, rolled_back.value) is None


async def test_different_projects_race_the_last_build_history_space(database: Database) -> None:
    actor = await seed_project_creator(database)
    first = (await create_project(database, actor)).project.project_id
    second = (
        await create_project(database, actor, name="second", key="history-second")
    ).project.project_id
    installation = actor.binding.installation_id
    organization = actor.organization_id
    principal = actor.access.actor_principal_id
    pipeline_id = PipelineId(uuid4())
    async with database.session() as session, session.begin():
        capacity = await session.get(RetainedHistoryCapacityRow, 1)
        assert capacity is not None
        capacity.ordinary_limit_bytes = _CHARGE

    barrier = asyncio.Barrier(2)

    async def compete(scope: ArtifactScopeDTO, key: str) -> bool:
        try:
            async with database.session() as session, session.begin():
                original = await _original(session, scope, principal, pipeline_id, key)
                await barrier.wait()
                await PostgresBuildHistoryReservationWriter(
                    session, safety_headroom=MockRetainedHistorySafetyHeadroom(installation)
                ).reserve_build(scope=scope, operation_id=original, pipeline_id=pipeline_id)
            return True
        except RetainedHistoryCapacityError:
            return False

    async with asyncio.timeout(10):
        outcomes = await asyncio.gather(
            compete(ArtifactScopeDTO(installation, organization, first), "first"),
            compete(ArtifactScopeDTO(installation, organization, second), "second"),
        )
    assert sorted(outcomes) == [False, True]
    async with database.session() as session:
        capacity = await session.get(RetainedHistoryCapacityRow, 1)
        assert capacity is not None and capacity.reserved_bytes == _CHARGE
        assert (
            await session.scalar(select(func.count()).select_from(RetainedHistoryReservationRow))
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.request_key.in_(("first", "second")))
            )
            == 1
        )


async def test_safety_headroom_failure_keeps_ordinary_build_history_uncommitted(
    database: Database,
) -> None:
    actor = await seed_project_creator(database)
    project = (await create_project(database, actor)).project.project_id
    scope = ArtifactScopeDTO(actor.binding.installation_id, actor.organization_id, project)
    pipeline_id = PipelineId(uuid4())
    safety = MockRetainedHistorySafetyHeadroom(scope.installation_id, available=False)

    original: OperationId | None = None
    with pytest.raises(DependencyUnavailableError, match="retained safety headroom"):
        async with database.session() as session, session.begin():
            original = await _original(
                session, scope, actor.access.actor_principal_id, pipeline_id, "safety-rejected"
            )
            await PostgresBuildHistoryReservationWriter(
                session, safety_headroom=safety
            ).reserve_build(scope=scope, operation_id=original, pipeline_id=pipeline_id)

    assert original is not None
    async with database.session() as session:
        capacity = await session.get(RetainedHistoryCapacityRow, 1)
        assert safety.checked == 1 and capacity is not None and capacity.reserved_bytes == 0
        assert await session.get(RetainedHistoryReservationRow, original.value) is None
        assert await session.get(IdempotencyReservationRow, original.value) is None
