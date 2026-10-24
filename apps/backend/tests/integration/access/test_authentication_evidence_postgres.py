"""Check evidence against the stored actor before either authorization consumer admits work."""

import os
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.access_scenarios import MockAccessScenarios, ProjectAuthorizationSeedDTO
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.project_grant_changes import create_project_grant_change_service

from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_operation_admission_request_dto import (
    ProjectOperationAdmissionRequestDTO,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.project_operation_admission_service import (
    ProjectOperationAdmissionService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_result_dto import (
    OperationReservationResultDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
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


async def _effects(
    database: Database, seed: ProjectAuthorizationSeedDTO
) -> tuple[int | None, int, int, int]:
    async with database.session() as session:
        return (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == seed.project_id.value)
            ),
            (await session.scalar(select(func.count()).select_from(IdempotencyReservationRow)))
            or 0,
            (await session.scalar(select(func.count()).select_from(ProjectActionGrantRow))) or 0,
            (await session.scalar(select(func.count()).select_from(AccessAuditEventRow))) or 0,
        )


async def _invoke(
    session: AsyncSession,
    seed: ProjectAuthorizationSeedDTO,
    access: AccessContextDTO,
    consumer: str,
) -> None:
    if consumer == "grant":
        await create_project_grant_change_service(session).assign_use_only(
            access=access,
            command=AssignProjectUseOnlyGrantCommand(
                seed.project_id, seed.principal_id, seed.action, 0
            ),
            context=OperationAdmissionContextDTO(
                key=IdempotencyKey("evidence-check"),
                method="POST",
                requested_route="/v1/projects/{project_id}/grants",
            ),
        )
    else:
        async with session.begin():
            await ProjectOperationAdmissionService(
                ActionAuthorizationService(PostgresProjectActionFactsReader(session)),
                IdempotencyService(PostgresOperationReservationWriter(session)),
            ).reserve(
                access=access,
                action_id=seed.action,
                request=ProjectOperationAdmissionRequestDTO(
                    seed.project_id,
                    "POST",
                    "/v1/test-operation",
                    IdempotencyKey("evidence-check"),
                    RequestFingerprint(b"F" * 32),
                ),
                expected_replay_kind=OperationReplayKind.SAFE_RESULT,
            )


async def _mock_unreachable_reservation(
    self: PostgresOperationReservationWriter, request: OperationReservationRequestDTO
) -> OperationReservationResultDTO:
    raise AssertionError("Invalid evidence must not reach reservation or replay lookup.")


@pytest.mark.asyncio
@pytest.mark.parametrize("consumer", ["grant", "admission"])
@pytest.mark.parametrize("family", ["browser", "oauth", "application"])
async def test_mismatched_evidence_stops_before_reservation_and_effects(
    database: Database, consumer: str, family: str
) -> None:
    """A human credential cannot represent an application, or a key represent a human."""
    async with database.session() as session, session.begin():
        seed = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
            principal_kind=PrincipalKind.HUMAN
            if family == "application"
            else PrincipalKind.APPLICATION,
        )
    evidence = (
        MockAuthenticationEvidence.application_key()
        if family == "application"
        else MockAuthenticationEvidence.human_oauth()
        if family == "oauth"
        else MockAuthenticationEvidence.browser()
    )
    access = AccessContextDTO(seed.principal_id, evidence)
    before = await _effects(database, seed)
    with patch.object(
        PostgresOperationReservationWriter, "reserve", new=_mock_unreachable_reservation
    ):
        async with database.session() as session:
            with pytest.raises(RuntimeError, match="principal kind"):
                await _invoke(session, seed, access, consumer)
    assert await _effects(database, seed) == before


@pytest.mark.asyncio
async def test_application_evidence_keeps_human_only_grants_forbidden(database: Database) -> None:
    """Correct application evidence still grants no human delegation authority."""
    async with database.session() as session, session.begin():
        seed = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
            principal_kind=PrincipalKind.APPLICATION,
        )
    before = await _effects(database, seed)
    access = AccessContextDTO(seed.principal_id, MockAuthenticationEvidence.application_key())
    with patch.object(
        PostgresOperationReservationWriter, "reserve", new=_mock_unreachable_reservation
    ):
        async with database.session() as session:
            with pytest.raises(AccessDeniedError):
                await _invoke(session, seed, access, "grant")
    assert await _effects(database, seed) == before
