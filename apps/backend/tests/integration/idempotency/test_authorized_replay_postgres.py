"""Verify that project retries use current authority and the verified caller."""

import os

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.access_scenarios import MockAccessScenarios

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.project_operation_admission_request_dto import (
    ProjectOperationAdmissionRequestDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    IdempotencyInProgressError,
)
from inframeld_backend.shared.application.services.project_operation_admission_service import (
    ProjectOperationAdmissionService,
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


async def _authorized_request(
    database: Database,
) -> tuple[AccessContextDTO, ActionId, ProjectOperationAdmissionRequestDTO]:
    """Commit a grant and describe the project request without caller scope fields."""
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
        )

    return (
        AccessContextDTO(actor_principal_id=scenario.principal_id),
        scenario.action,
        ProjectOperationAdmissionRequestDTO(
            project_id=scenario.project_id,
            method="POST",
            requested_route="/v1/projects/{project_id}/builds",
            key=IdempotencyKey("build-request-1"),
            fingerprint=b"\x01" * 32,
        ),
    )


def _service_and_writer(
    session: AsyncSession,
) -> tuple[ProjectOperationAdmissionService, PostgresOperationReservationWriter]:
    writer = PostgresOperationReservationWriter(session)
    service = ProjectOperationAdmissionService(
        ActionAuthorizationService(PostgresProjectActionFactsReader(session)),
        writer,
    )
    return service, writer


@pytest.mark.asyncio
async def test_revoked_project_grant_blocks_replay(database: Database) -> None:
    """A saved reservation cannot bypass a grant revoked after the first request."""
    access, action_id, request = await _authorized_request(database)

    async with database.session() as session, session.begin():
        service, writer = _service_and_writer(session)
        first = await service.reserve(access=access, action_id=action_id, request=request)
        await writer.mark_replayable(first.operation_id, OperationReplayKind.SAFE_RESULT)

    assert first.created

    async with database.session() as session, session.begin():
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == request.project_id.value,
                ProjectActionGrantRow.recipient_principal_id == access.actor_principal_id.value,
                ProjectActionGrantRow.action == action_id.value,
            )
        )

    async with database.session() as session, session.begin():
        service, _ = _service_and_writer(session)
        with pytest.raises(AccessDeniedError):
            await service.reserve(access=access, action_id=action_id, request=request)


@pytest.mark.asyncio
async def test_reservation_uses_authorized_principal_and_organization(database: Database) -> None:
    """Store the authenticated principal and project organization, not request claims."""
    access, action_id, request = await _authorized_request(database)

    async with database.session() as session, session.begin():
        service, _ = _service_and_writer(session)
        result = await service.reserve(access=access, action_id=action_id, request=request)
        scope_query = select(
            IdempotencyReservationRow.principal_id,
            IdempotencyReservationRow.organization_id,
            IdempotencyReservationRow.project_id,
        ).where(IdempotencyReservationRow.operation_id == result.operation_id.value)
        stored_scope = (await session.execute(scope_query)).tuples().one()
        expected_organization_id = await session.scalar(
            select(ProjectRow.organization_id).where(ProjectRow.id == request.project_id.value)
        )

    assert result.created
    assert stored_scope == (
        access.actor_principal_id.value,
        expected_organization_id,
        request.project_id.value,
    )


@pytest.mark.asyncio
async def test_unfinished_retry_reports_the_original_operation(database: Database) -> None:
    """A matching retry cannot start a second unfinished operation."""
    access, action_id, request = await _authorized_request(database)

    async with database.session() as session, session.begin():
        service, _ = _service_and_writer(session)
        first = await service.reserve(access=access, action_id=action_id, request=request)

    async with database.session() as session, session.begin():
        service, _ = _service_and_writer(session)
        with pytest.raises(IdempotencyInProgressError) as caught:
            await service.reserve(access=access, action_id=action_id, request=request)

    assert caught.value.operation_id == first.operation_id
    assert caught.value.retry_after_seconds > 0


@pytest.mark.asyncio
async def test_accepted_async_retry_returns_original_operation(
    database: Database,
) -> None:
    """After acceptance, a matching retry reuses the original operation."""
    access, action_id, request = await _authorized_request(database)

    async with database.session() as session, session.begin():
        service, writer = _service_and_writer(session)
        first = await service.reserve(
            access=access,
            action_id=action_id,
            request=request,
        )
        await writer.mark_replayable(
            first.operation_id,
            OperationReplayKind.ASYNC_JOB,
        )

    async with database.session() as session, session.begin():
        service, _ = _service_and_writer(session)
        retry = await service.reserve(
            access=access,
            action_id=action_id,
            request=request,
        )

    assert first.created
    assert not retry.created
    assert retry.operation_id == first.operation_id
    assert retry.replay_kind is OperationReplayKind.ASYNC_JOB
