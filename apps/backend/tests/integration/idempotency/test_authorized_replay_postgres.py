"""Verify that project retries use current authority and the verified caller."""

import os
from dataclasses import dataclass, replace
from typing import override
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
    ProjectActionAuthorizationRequestDTO,
)
from inframeld_backend.access.application.dtos.project_operation_admission_request_dto import (
    ProjectOperationAdmissionRequestDTO,
)
from inframeld_backend.access.application.protocols.action_authorizer import ActionAuthorizer
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.project_operation_admission_service import (
    ProjectOperationAdmissionService,
)
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    IdempotencyInProgressError,
)
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


@dataclass(frozen=True, slots=True)
class MockAuthorizedOrganizationScopeDTO(AuthorizedOperationScope[None]):
    """Supply organization scope to qualify storage, without modeling a new permission."""

    organization_id: OrganizationId
    project_id: None = None


class MockMismatchedActionAuthorizer(ActionAuthorizer):
    """Load real current authority, then simulate returning another project's scope."""

    def __init__(self, authorizer: ActionAuthorizer, wrong_project_id: ProjectId) -> None:
        self._authorizer = authorizer
        self._wrong_project_id = wrong_project_id

    @override
    async def require_authorization(
        self, *, access: AccessContextDTO, request: ProjectActionAuthorizationRequestDTO
    ) -> ProjectActionAuthorizationDTO:
        authorization = await self._authorizer.require_authorization(access=access, request=request)
        return replace(authorization, project_id=self._wrong_project_id)


@pytest.mark.asyncio
async def test_organization_scoped_retry_preserves_scope_fingerprint_and_expiry(
    database: Database,
) -> None:
    """A retry without a project must find the original organization-scoped operation."""
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=False, has_action_grant=False
        )
    access = AccessContextDTO(
        scenario.principal_id, authentication_evidence=MockAuthenticationEvidence.browser()
    )
    authorization = MockAuthorizedOrganizationScopeDTO(scenario.organization_id)
    context = OperationAdmissionContextDTO(
        method="PATCH",
        requested_route="/v1/test-organization-operation",
        key=IdempotencyKey("organization-retry-1"),
    )
    fingerprint = RequestFingerprint(bytes(range(32)))

    async with database.session() as session, session.begin():
        service = IdempotencyService(PostgresOperationReservationWriter(session))
        first = await service.find_or_reserve(
            context=context,
            access=access,
            authorization=authorization,
            fingerprint=fingerprint,
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
        )
        assert isinstance(first, NewOperationReservationDTO)
        completed = await service.record_completed_result(
            first, replay_kind=OperationReplayKind.SAFE_RESULT
        )
        assert isinstance(completed, CompletedSynchronousOperationDTO)
        assert completed.created is True
        assert completed.operation_id == first.operation_id

    async with database.session() as session, session.begin():
        service = IdempotencyService(PostgresOperationReservationWriter(session))
        retry = await service.find_or_reserve(
            context=context,
            access=access,
            authorization=authorization,
            fingerprint=fingerprint,
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
        )
        assert isinstance(retry, CompletedSynchronousOperationDTO)
        assert retry.created is False
        assert retry.operation_id == first.operation_id
        assert retry.expires_at == completed.expires_at
        assert retry.replay_kind is OperationReplayKind.SAFE_RESULT

    async with database.session() as session:
        stored = await session.get(IdempotencyReservationRow, first.operation_id.value)
        assert stored is not None
        assert stored.principal_id == access.actor_principal_id.value
        assert stored.organization_id == scenario.organization_id.value
        assert stored.project_id is None
        assert stored.request_fingerprint == fingerprint.value
        assert stored.method == context.method
        assert stored.requested_route == context.requested_route
        assert stored.request_key == context.key.value
        assert stored.expires_at == completed.expires_at
        assert stored.state is OperationReservationState.REPLAYABLE
        assert stored.replay_kind is OperationReplayKind.SAFE_RESULT
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow)) == 1
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
        AccessContextDTO(
            actor_principal_id=scenario.principal_id,
            authentication_evidence=MockAuthenticationEvidence.browser(),
        ),
        scenario.action,
        ProjectOperationAdmissionRequestDTO(
            project_id=scenario.project_id,
            method="POST",
            requested_route="/v1/projects/{project_id}/builds",
            key=IdempotencyKey("build-request-1"),
            fingerprint=RequestFingerprint(b"\x01" * 32),
        ),
    )


def _service_and_writer(
    session: AsyncSession,
) -> tuple[ProjectOperationAdmissionService, PostgresOperationReservationWriter]:
    writer = PostgresOperationReservationWriter(session)
    service = ProjectOperationAdmissionService(
        authorizer=ActionAuthorizationService(PostgresProjectActionFactsReader(session)),
        idempotency=IdempotencyService(writer),
    )
    return service, writer


@pytest.mark.asyncio
@pytest.mark.parametrize("replay", [False, True], ids=["new", "replay"])
async def test_mismatched_admission_scope_preserves_records_and_caller_transaction(
    database: Database, replay: bool
) -> None:
    """Wrong scope blocks lookup, and the owning operation still decides when to roll back."""
    access, action_id, request = await _authorized_request(database)
    wrong_project_id = ProjectId(uuid4())
    async with database.session() as session, session.begin():
        organization_id = await session.scalar(
            select(ProjectRow.organization_id).where(ProjectRow.id == request.project_id.value)
        )
        assert organization_id is not None
        session.add(
            ProjectRow(
                id=wrong_project_id.value,
                organization_id=organization_id,
                name="Billing",
                status=ProjectStatus.ACTIVE,
            )
        )

    original: CompletedSynchronousOperationDTO | None = None
    if replay:
        async with database.session() as session, session.begin():
            service, writer = _service_and_writer(session)
            operation = await service.reserve(
                access=access,
                action_id=action_id,
                request=request,
                expected_replay_kind=OperationReplayKind.SAFE_RESULT,
            )
            assert isinstance(operation, NewOperationReservationDTO)
            completed = await IdempotencyService(writer).record_completed_result(
                operation, replay_kind=OperationReplayKind.SAFE_RESULT
            )
            assert isinstance(completed, CompletedSynchronousOperationDTO)
            original = completed

    async with database.session() as session:
        with pytest.raises(RuntimeError, match="The caller requested rollback"):
            async with session.begin():
                service = ProjectOperationAdmissionService(
                    authorizer=MockMismatchedActionAuthorizer(
                        ActionAuthorizationService(PostgresProjectActionFactsReader(session)),
                        wrong_project_id,
                    ),
                    idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
                )
                with pytest.raises(
                    RuntimeError, match="Authorization returned a different project"
                ):
                    await service.reserve(
                        access=access,
                        action_id=action_id,
                        request=request,
                        expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                    )
                assert session.in_transaction()
                raise RuntimeError("The caller requested rollback.")
        assert not session.in_transaction()

    async with database.session() as session:
        reservations = (
            await session.scalars(
                select(IdempotencyReservationRow).where(
                    IdempotencyReservationRow.principal_id == access.actor_principal_id.value
                )
            )
        ).all()
        revisions = (
            await session.scalars(
                select(ProjectRow.access_revision).where(
                    ProjectRow.id.in_((request.project_id.value, wrong_project_id.value))
                )
            )
        ).all()
        assert revisions == [0, 0]
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectActionGrantRow)
                .where(
                    ProjectActionGrantRow.recipient_principal_id == access.actor_principal_id.value
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.actor_principal_id == access.actor_principal_id.value)
            )
            == 0
        )
        assert len(reservations) == int(replay)
        if original is not None:
            assert reservations[0].operation_id == original.operation_id.value
            assert reservations[0].project_id == request.project_id.value
            assert reservations[0].organization_id == organization_id
            assert reservations[0].request_fingerprint == request.fingerprint.value
            assert reservations[0].request_key == request.key.value
            assert reservations[0].state is OperationReservationState.REPLAYABLE
            assert reservations[0].replay_kind is OperationReplayKind.SAFE_RESULT
            assert reservations[0].expires_at == original.expires_at


@pytest.mark.asyncio
async def test_revoked_project_grant_blocks_replay(database: Database) -> None:
    """A saved reservation cannot bypass a grant revoked after the first request."""
    access, action_id, request = await _authorized_request(database)

    async with database.session() as session, session.begin():
        service, writer = _service_and_writer(session)
        first = await service.reserve(
            access=access,
            action_id=action_id,
            request=request,
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
        )
        await writer.mark_replayable(first.operation_id, OperationReplayKind.SAFE_RESULT)

    assert isinstance(first, NewOperationReservationDTO)

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
            await service.reserve(
                access=access,
                action_id=action_id,
                request=request,
                expected_replay_kind=OperationReplayKind.SAFE_RESULT,
            )


@pytest.mark.asyncio
async def test_reservation_uses_authorized_principal_and_organization(database: Database) -> None:
    """Store the authenticated principal and project organization, not request claims."""
    access, action_id, request = await _authorized_request(database)

    async with database.session() as session, session.begin():
        service, _ = _service_and_writer(session)
        result = await service.reserve(
            access=access,
            action_id=action_id,
            request=request,
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
        )
        scope_query = select(
            IdempotencyReservationRow.principal_id,
            IdempotencyReservationRow.organization_id,
            IdempotencyReservationRow.project_id,
        ).where(IdempotencyReservationRow.operation_id == result.operation_id.value)
        stored_scope = (await session.execute(scope_query)).tuples().one()
        expected_organization_id = await session.scalar(
            select(ProjectRow.organization_id).where(ProjectRow.id == request.project_id.value)
        )

    assert isinstance(result, NewOperationReservationDTO)
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
        first = await service.reserve(
            access=access,
            action_id=action_id,
            request=request,
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
        )

    async with database.session() as session, session.begin():
        service, _ = _service_and_writer(session)
        with pytest.raises(IdempotencyInProgressError) as caught:
            await service.reserve(
                access=access,
                action_id=action_id,
                request=request,
                expected_replay_kind=OperationReplayKind.SAFE_RESULT,
            )

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
            expected_replay_kind=OperationReplayKind.ASYNC_JOB,
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
            expected_replay_kind=OperationReplayKind.ASYNC_JOB,
        )

    assert isinstance(first, NewOperationReservationDTO)
    assert isinstance(retry, AcceptedAsyncOperationDTO)
    assert not retry.created
    assert retry.operation_id == first.operation_id
    assert retry.expires_at is None
    async with database.session() as session:
        stored = await session.get(IdempotencyReservationRow, first.operation_id.value)
        assert stored is not None
        assert stored.state is OperationReservationState.REPLAYABLE
        assert stored.replay_kind is OperationReplayKind.ASYNC_JOB


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        OperationReplayKind.SAFE_RESULT,
        OperationReplayKind.ISSUED_SECRET,
        OperationReplayKind.ANSWER_RECEIPT,
    ],
)
async def test_completed_synchronous_admission_replays_original_metadata(
    database: Database, kind: OperationReplayKind
) -> None:
    """All synchronous replay categories retain their original identity and deadline."""
    access, action_id, request = await _authorized_request(database)
    async with database.session() as session, session.begin():
        service, writer = _service_and_writer(session)
        first = await service.reserve(
            access=access, action_id=action_id, request=request, expected_replay_kind=kind
        )
        assert isinstance(first, NewOperationReservationDTO)
        expiry = await writer.mark_replayable(first.operation_id, kind)
        assert expiry is not None
    async with database.session() as session, session.begin():
        service, _ = _service_and_writer(session)
        retry = await service.reserve(
            access=access, action_id=action_id, request=request, expected_replay_kind=kind
        )
        assert isinstance(retry, CompletedSynchronousOperationDTO)
        assert retry.created is False
        assert retry.operation_id == first.operation_id
        assert retry.replay_kind is kind
        assert retry.expires_at == expiry
        count = await session.scalar(
            select(func.count())
            .select_from(IdempotencyReservationRow)
            .where(IdempotencyReservationRow.principal_id == access.actor_principal_id.value)
        )
        assert count == 1


@pytest.mark.asyncio
async def test_recovery_required_admission_preserves_original_operation(database: Database) -> None:
    """Uncertain work stays reserved and cannot become a completed replay or new operation."""
    access, action_id, request = await _authorized_request(database)
    async with database.session() as session, session.begin():
        service, writer = _service_and_writer(session)
        first = await service.reserve(
            access=access,
            action_id=action_id,
            request=request,
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
        )
        assert isinstance(first, NewOperationReservationDTO)
        await writer.mark_recovery_required(first.operation_id)
    async with database.session() as session, session.begin():
        service, _ = _service_and_writer(session)
        retry = await service.reserve(
            access=access,
            action_id=action_id,
            request=request,
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
        )
        assert retry == RecoveryRequiredOperationDTO(first.operation_id)
        stored = await session.get(IdempotencyReservationRow, first.operation_id.value)
        assert stored is not None
        assert stored.state is OperationReservationState.RECOVERY_REQUIRED
        assert stored.replay_kind is None
        assert stored.expires_at is None
        count = await session.scalar(select(func.count()).select_from(IdempotencyReservationRow))
        assert count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored_kind, requested_kind",
    [
        (OperationReplayKind.SAFE_RESULT, OperationReplayKind.ASYNC_JOB),
        (OperationReplayKind.ASYNC_JOB, OperationReplayKind.SAFE_RESULT),
    ],
)
async def test_incompatible_replay_kind_cannot_replace_original_admission(
    database: Database, stored_kind: OperationReplayKind, requested_kind: OperationReplayKind
) -> None:
    access, action_id, request = await _authorized_request(database)
    async with database.session() as session, session.begin():
        service, writer = _service_and_writer(session)
        first = await service.reserve(
            access=access, action_id=action_id, request=request, expected_replay_kind=stored_kind
        )
        assert isinstance(first, NewOperationReservationDTO)
        expiry = await writer.mark_replayable(first.operation_id, stored_kind)
    with pytest.raises(ConflictError):
        async with database.session() as session, session.begin():
            service, _ = _service_and_writer(session)
            await service.reserve(
                access=access,
                action_id=action_id,
                request=request,
                expected_replay_kind=requested_kind,
            )
    async with database.session() as session:
        stored = await session.get(IdempotencyReservationRow, first.operation_id.value)
        assert stored is not None
        assert stored.state is OperationReservationState.REPLAYABLE
        assert stored.replay_kind is stored_kind
        assert stored.expires_at == expiry
        count = await session.scalar(select(func.count()).select_from(IdempotencyReservationRow))
        assert count == 1


@pytest.mark.asyncio
async def test_shared_admission_keeps_the_callers_rollback_boundary(database: Database) -> None:
    """The admission helper must not independently commit its new reservation."""
    access, action_id, request = await _authorized_request(database)
    with pytest.raises(RuntimeError, match="owning operation failed"):
        async with database.session() as session, session.begin():
            service, _ = _service_and_writer(session)
            await service.reserve(
                access=access,
                action_id=action_id,
                request=request,
                expected_replay_kind=OperationReplayKind.SAFE_RESULT,
            )
            raise RuntimeError("owning operation failed")
    async with database.session() as session:
        count = await session.scalar(select(func.count()).select_from(IdempotencyReservationRow))
        assert count == 0
