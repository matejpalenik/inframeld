"""Verify that a project grant change saves its current and historical records."""

import asyncio
import os
from dataclasses import replace
from typing import override
from uuid import uuid4

import pytest
from sqlalchemy import ARRAY, Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.project_grant_changes import create_project_grant_change_service

from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_grant_authorization_dto import (
    ProjectGrantAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_use_only_grant_authorization_request_dto import (
    ProjectUseOnlyGrantAuthorizationRequestDTO,
)
from inframeld_backend.access.application.protocols.project_grant_authorizer import (
    ProjectGrantAuthorizer,
)
from inframeld_backend.access.application.services.project_grant_authorization_service import (
    ProjectGrantAuthorizationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_project_grant_change_facts_reader import (
    PostgresProjectGrantChangeFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import (
    AccessAuditEventRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import (
    ProjectMembershipRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    IdempotencyKeyReusedError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


class MockMismatchedProjectGrantAuthorizer(ProjectGrantAuthorizer):
    """Acquire real authorization locks, then return another project's ID by mistake."""

    def __init__(self, authorizer: ProjectGrantAuthorizer, wrong_project_id: ProjectId) -> None:
        self._authorizer = authorizer
        self._wrong_project_id = wrong_project_id

    @override
    async def require_authorization(
        self, *, access: AccessContextDTO, request: ProjectUseOnlyGrantAuthorizationRequestDTO
    ) -> ProjectGrantAuthorizationDTO:
        authorization = await self._authorizer.require_authorization(access=access, request=request)
        return replace(authorization, project_id=self._wrong_project_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("replay", [False, True], ids=["new", "replay"])
async def test_mismatched_authorization_rolls_back_without_changing_either_project(
    database: Database, replay: bool
) -> None:
    """A scope mismatch must preserve both projects and any existing completed operation."""
    recipient_id = PrincipalId(uuid4())
    wrong_project_id = ProjectId(uuid4())
    action_id = ActionId("create-access-groups")
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=True, has_action_grant=False
        )
        session.add_all(
            [
                PrincipalRow(
                    id=recipient_id.value,
                    organization_id=scenario.organization_id.value,
                    kind=PrincipalKind.HUMAN,
                    status=PrincipalStatus.ACTIVE,
                    display_name="Bob",
                ),
                ProjectRow(
                    id=wrong_project_id.value,
                    organization_id=scenario.organization_id.value,
                    name="Billing",
                    status=ProjectStatus.ACTIVE,
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                ProjectMembershipRow(
                    project_id=scenario.project_id.value,
                    principal_id=recipient_id.value,
                    organization_id=scenario.organization_id.value,
                    principal_kind=PrincipalKind.HUMAN,
                ),
                ProjectActionGrantRow(
                    project_id=scenario.project_id.value,
                    recipient_principal_id=scenario.principal_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=action_id.value,
                    can_grant=True,
                ),
            ]
        )

    access = AccessContextDTO(scenario.principal_id)
    command = AssignProjectUseOnlyGrantCommand(
        scenario.project_id, recipient_id, action_id, expected_access_revision=0
    )
    context = OperationAdmissionContextDTO(
        method="POST",
        requested_route="/v1/projects/{project_id}/grants",
        key=IdempotencyKey("grant-scope-mismatch"),
    )
    original: CompletedSynchronousOperationDTO | None = None
    if replay:
        async with database.session() as session:
            original = await create_project_grant_change_service(session).assign_use_only(
                access=access, command=command, context=context
            )

    async with database.session() as session:
        authorizer = MockMismatchedProjectGrantAuthorizer(
            ProjectGrantAuthorizationService(PostgresProjectGrantChangeFactsReader(session)),
            wrong_project_id,
        )
        service = create_project_grant_change_service(session, authorizer=authorizer)
        with pytest.raises(RuntimeError, match="Authorization returned a different project"):
            await service.assign_use_only(access=access, command=command, context=context)
        assert not session.in_transaction()

    async with database.session() as session:
        requested_revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == scenario.project_id.value)
        )
        wrong_revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == wrong_project_id.value)
        )
        grants = (
            await session.scalars(
                select(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.recipient_principal_id == recipient_id.value
                )
            )
        ).all()
        audit_count = await session.scalar(
            select(func.count())
            .select_from(AccessAuditEventRow)
            .where(AccessAuditEventRow.actor_principal_id == scenario.principal_id.value)
        )
        reservations = (
            await session.scalars(
                select(IdempotencyReservationRow).where(
                    IdempotencyReservationRow.principal_id == scenario.principal_id.value
                )
            )
        ).all()

        expected_count = int(replay)
        assert requested_revision == expected_count
        assert wrong_revision == 0
        assert len(grants) == expected_count
        assert all(grant.project_id == scenario.project_id.value for grant in grants)
        assert audit_count == expected_count
        assert len(reservations) == expected_count
        if original is not None:
            assert reservations[0].operation_id == original.operation_id.value
            assert reservations[0].project_id == scenario.project_id.value
            assert reservations[0].state is OperationReservationState.REPLAYABLE
            assert reservations[0].replay_kind is OperationReplayKind.SAFE_RESULT
            assert reservations[0].expires_at == original.expires_at


@pytest.mark.asyncio
async def test_assign_use_only_saves_grant_revision_audit_and_reservation(
    database: Database,
) -> None:
    """A successful decision commits its grant and recovery records together."""
    action_id = ActionId("create-access-groups")
    recipient_id = PrincipalId(uuid4())

    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=False,
        )

        session.add(
            PrincipalRow(
                id=recipient_id.value,
                organization_id=scenario.organization_id.value,
                kind=PrincipalKind.HUMAN,
                status=PrincipalStatus.ACTIVE,
                display_name="Bob",
            )
        )
        await session.flush()

        session.add_all(
            [
                ProjectMembershipRow(
                    project_id=scenario.project_id.value,
                    principal_id=recipient_id.value,
                    organization_id=scenario.organization_id.value,
                    principal_kind=PrincipalKind.HUMAN,
                ),
                ProjectActionGrantRow(
                    project_id=scenario.project_id.value,
                    recipient_principal_id=scenario.principal_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=action_id.value,
                    can_grant=True,
                ),
            ]
        )

    request = OperationAdmissionContextDTO(
        method="POST",
        requested_route="/v1/projects/{project_id}/grants",
        key=IdempotencyKey("grant-bob-1"),
    )

    async with database.session() as session:
        service = create_project_grant_change_service(session)
        await service.assign_use_only(
            access=AccessContextDTO(actor_principal_id=scenario.principal_id),
            context=request,
            command=AssignProjectUseOnlyGrantCommand(
                project_id=scenario.project_id,
                recipient_principal_id=recipient_id,
                action_id=action_id,
                expected_access_revision=0,
            ),
        )

    async with database.session() as session:
        grants = (
            await session.scalars(
                select(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == scenario.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id == recipient_id.value,
                    ProjectActionGrantRow.action == action_id.value,
                )
            )
        ).all()
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == scenario.project_id.value)
        )
        audit_events = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.project_id == scenario.project_id.value,
                    AccessAuditEventRow.actor_principal_id == scenario.principal_id.value,
                    AccessAuditEventRow.affected_principal_id == recipient_id.value,
                    AccessAuditEventRow.action == action_id.value,
                )
            )
        ).all()
        reservations = (
            await session.scalars(
                select(IdempotencyReservationRow).where(
                    IdempotencyReservationRow.principal_id == scenario.principal_id.value,
                    IdempotencyReservationRow.project_id == scenario.project_id.value,
                    IdempotencyReservationRow.request_key == request.key.value,
                )
            )
        ).all()

    assert len(grants) == 1
    assert grants[0].can_grant is False
    assert grants[0].assigned_by_principal_id == scenario.principal_id.value
    assert revision == 1

    assert len(audit_events) == 1
    assert audit_events[0].organization_id == scenario.organization_id.value
    assert audit_events[0].target_id == scenario.project_id.value
    assert audit_events[0].actor_kind == PrincipalKind.HUMAN.value
    assert audit_events[0].event_type == "project_action_grant_assigned"
    assert audit_events[0].target_kind == "project"
    assert audit_events[0].after_values == {"can_grant": False}
    assert audit_events[0].before_values is None
    assert audit_events[0].actor_reference is None
    assert audit_events[0].reason is None

    assert len(reservations) == 1
    assert reservations[0].organization_id == scenario.organization_id.value
    assert reservations[0].state is OperationReservationState.REPLAYABLE
    assert reservations[0].replay_kind is OperationReplayKind.SAFE_RESULT
    assert audit_events[0].correlation_id == reservations[0].operation_id


@pytest.mark.asyncio
async def test_assign_use_only_replay_keeps_original_operation_without_writing_again(
    database: Database,
) -> None:
    """A lost response can be retried after commit without repeating the change."""
    action_id = ActionId("create-access-groups")
    recipient_id = PrincipalId(uuid4())

    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=False,
        )
        session.add(
            PrincipalRow(
                id=recipient_id.value,
                organization_id=scenario.organization_id.value,
                kind=PrincipalKind.HUMAN,
                status=PrincipalStatus.ACTIVE,
                display_name="Bob",
            )
        )
        await session.flush()
        session.add_all(
            [
                ProjectMembershipRow(
                    project_id=scenario.project_id.value,
                    principal_id=recipient_id.value,
                    organization_id=scenario.organization_id.value,
                    principal_kind=PrincipalKind.HUMAN,
                ),
                ProjectActionGrantRow(
                    project_id=scenario.project_id.value,
                    recipient_principal_id=scenario.principal_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=action_id.value,
                    can_grant=True,
                ),
            ]
        )

    request = OperationAdmissionContextDTO(
        method="POST",
        requested_route="/v1/projects/{project_id}/grants",
        key=IdempotencyKey("grant-bob-replay-1"),
    )
    access = AccessContextDTO(actor_principal_id=scenario.principal_id)

    async with database.session() as session:
        service = create_project_grant_change_service(session)
        first_result = await service.assign_use_only(
            access=access,
            context=request,
            command=AssignProjectUseOnlyGrantCommand(
                project_id=scenario.project_id,
                recipient_principal_id=recipient_id,
                action_id=action_id,
                expected_access_revision=0,
            ),
        )

    # The first transaction has committed, but the caller repeats its old request.
    async with database.session() as session:
        service = create_project_grant_change_service(session)
        replay_result = await service.assign_use_only(
            access=access,
            context=request,
            command=AssignProjectUseOnlyGrantCommand(
                project_id=scenario.project_id,
                recipient_principal_id=recipient_id,
                action_id=action_id,
                expected_access_revision=0,
            ),
        )

    async with database.session() as session:
        grants = (
            await session.scalars(
                select(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == scenario.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id == recipient_id.value,
                    ProjectActionGrantRow.action == action_id.value,
                )
            )
        ).all()
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == scenario.project_id.value)
        )
        audit_events = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.project_id == scenario.project_id.value,
                    AccessAuditEventRow.affected_principal_id == recipient_id.value,
                    AccessAuditEventRow.action == action_id.value,
                )
            )
        ).all()
        reservations = (
            await session.scalars(
                select(IdempotencyReservationRow).where(
                    IdempotencyReservationRow.principal_id == scenario.principal_id.value,
                    IdempotencyReservationRow.project_id == scenario.project_id.value,
                    IdempotencyReservationRow.request_key == request.key.value,
                )
            )
        ).all()

    assert first_result.created is True
    assert replay_result.created is False
    assert replay_result.operation_id == first_result.operation_id
    assert isinstance(replay_result, CompletedSynchronousOperationDTO)
    assert replay_result.replay_kind is OperationReplayKind.SAFE_RESULT

    assert len(grants) == 1
    assert revision == 1
    assert len(audit_events) == 1
    assert len(reservations) == 1
    assert reservations[0].operation_id == first_result.operation_id.value


@pytest.mark.asyncio
async def test_new_key_with_stale_revision_rolls_back_entire_grant_change(
    database: Database,
) -> None:
    """A new decision based on old state saves no grant, audit, or reservation."""
    action_id = ActionId("create-access-groups")
    recipient_id = PrincipalId(uuid4())

    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=False,
        )
        session.add(
            PrincipalRow(
                id=recipient_id.value,
                organization_id=scenario.organization_id.value,
                kind=PrincipalKind.HUMAN,
                status=PrincipalStatus.ACTIVE,
                display_name="Bob",
            )
        )
        await session.flush()
        session.add_all(
            [
                ProjectMembershipRow(
                    project_id=scenario.project_id.value,
                    principal_id=recipient_id.value,
                    organization_id=scenario.organization_id.value,
                    principal_kind=PrincipalKind.HUMAN,
                ),
                ProjectActionGrantRow(
                    project_id=scenario.project_id.value,
                    recipient_principal_id=scenario.principal_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=action_id.value,
                    can_grant=True,
                ),
            ]
        )

    request = OperationAdmissionContextDTO(
        method="POST",
        requested_route="/v1/projects/{project_id}/grants",
        key=IdempotencyKey("grant-bob-original"),
    )
    access = AccessContextDTO(actor_principal_id=scenario.principal_id)

    async with database.session() as session:
        service = create_project_grant_change_service(session)
        await service.assign_use_only(
            access=access,
            context=request,
            command=AssignProjectUseOnlyGrantCommand(
                project_id=scenario.project_id,
                recipient_principal_id=recipient_id,
                action_id=action_id,
                expected_access_revision=0,
            ),
        )

    # This key represents a new command, unlike a retry of the original key.
    stale_request = replace(
        request,
        key=IdempotencyKey("grant-bob-new-command"),
    )

    # The application operation rolls back its reservation before propagating the failure.
    with pytest.raises(StaleRevisionError):
        async with database.session() as session:
            service = create_project_grant_change_service(session)
            await service.assign_use_only(
                access=access,
                context=stale_request,
                command=AssignProjectUseOnlyGrantCommand(
                    project_id=scenario.project_id,
                    recipient_principal_id=recipient_id,
                    action_id=action_id,
                    expected_access_revision=0,
                ),
            )

    async with database.session() as session:
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == scenario.project_id.value)
        )
        grants = (
            await session.scalars(
                select(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == scenario.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id == recipient_id.value,
                    ProjectActionGrantRow.action == action_id.value,
                )
            )
        ).all()
        audit_events = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.project_id == scenario.project_id.value,
                    AccessAuditEventRow.affected_principal_id == recipient_id.value,
                    AccessAuditEventRow.action == action_id.value,
                )
            )
        ).all()
        reservations = (
            await session.scalars(
                select(IdempotencyReservationRow).where(
                    IdempotencyReservationRow.principal_id == scenario.principal_id.value,
                    IdempotencyReservationRow.project_id == scenario.project_id.value,
                )
            )
        ).all()

    assert revision == 1
    assert len(grants) == 1
    assert len(audit_events) == 1
    assert len(reservations) == 1
    assert reservations[0].request_key == request.key.value


@pytest.mark.asyncio
async def test_same_key_cannot_change_grant_recipient(database: Database) -> None:
    """A retry key for Bob cannot be reused to grant Carol instead."""
    action_id = ActionId("create-access-groups")
    bob_id = PrincipalId(uuid4())
    carol_id = PrincipalId(uuid4())

    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=False,
        )
        session.add_all(
            [
                PrincipalRow(
                    id=principal_id.value,
                    organization_id=scenario.organization_id.value,
                    kind=PrincipalKind.HUMAN,
                    status=PrincipalStatus.ACTIVE,
                    display_name=name,
                )
                for principal_id, name in ((bob_id, "Bob"), (carol_id, "Carol"))
            ]
        )
        await session.flush()
        session.add_all(
            [
                ProjectMembershipRow(
                    project_id=scenario.project_id.value,
                    principal_id=principal_id.value,
                    organization_id=scenario.organization_id.value,
                    principal_kind=PrincipalKind.HUMAN,
                )
                for principal_id in (bob_id, carol_id)
            ]
            + [
                ProjectActionGrantRow(
                    project_id=scenario.project_id.value,
                    recipient_principal_id=scenario.principal_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=action_id.value,
                    can_grant=True,
                )
            ]
        )

    request = OperationAdmissionContextDTO(
        method="POST",
        requested_route="/v1/projects/{project_id}/grants",
        key=IdempotencyKey("grant-recipient-1"),
    )
    access = AccessContextDTO(actor_principal_id=scenario.principal_id)

    async with database.session() as session:
        service = create_project_grant_change_service(session)
        await service.assign_use_only(
            access=access,
            context=request,
            command=AssignProjectUseOnlyGrantCommand(
                project_id=scenario.project_id,
                recipient_principal_id=bob_id,
                action_id=action_id,
                expected_access_revision=0,
            ),
        )

    with pytest.raises(IdempotencyKeyReusedError):
        async with database.session() as session:
            service = create_project_grant_change_service(session)
            await service.assign_use_only(
                access=access,
                context=request,
                command=AssignProjectUseOnlyGrantCommand(
                    project_id=scenario.project_id,
                    recipient_principal_id=carol_id,
                    action_id=action_id,
                    expected_access_revision=0,
                ),
            )

    async with database.session() as session:
        granted_recipients = (
            await session.scalars(
                select(ProjectActionGrantRow.recipient_principal_id).where(
                    ProjectActionGrantRow.project_id == scenario.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id.in_(
                        (bob_id.value, carol_id.value)
                    ),
                    ProjectActionGrantRow.action == action_id.value,
                )
            )
        ).all()
        audited_recipients = (
            await session.scalars(
                select(AccessAuditEventRow.affected_principal_id).where(
                    AccessAuditEventRow.project_id == scenario.project_id.value,
                    AccessAuditEventRow.action == action_id.value,
                )
            )
        ).all()
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == scenario.project_id.value)
        )

    assert granted_recipients == [bob_id.value]
    assert audited_recipients == [bob_id.value]
    assert revision == 1


@pytest.mark.asyncio
async def test_concurrent_equal_grants_commit_one_change(
    database: Database,
) -> None:
    """Two simultaneous copies of one command share its committed outcome."""
    action_id = ActionId("create-access-groups")
    recipient_id = PrincipalId(uuid4())

    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=False,
        )
        session.add(
            PrincipalRow(
                id=recipient_id.value,
                organization_id=scenario.organization_id.value,
                kind=PrincipalKind.HUMAN,
                status=PrincipalStatus.ACTIVE,
                display_name="Bob",
            )
        )
        await session.flush()
        session.add_all(
            [
                ProjectMembershipRow(
                    project_id=scenario.project_id.value,
                    principal_id=recipient_id.value,
                    organization_id=scenario.organization_id.value,
                    principal_kind=PrincipalKind.HUMAN,
                ),
                ProjectActionGrantRow(
                    project_id=scenario.project_id.value,
                    recipient_principal_id=scenario.principal_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=action_id.value,
                    can_grant=True,
                ),
            ]
        )

    request = OperationAdmissionContextDTO(
        method="POST",
        requested_route="/v1/projects/{project_id}/grants",
        key=IdempotencyKey("grant-bob-concurrent-1"),
    )
    access = AccessContextDTO(actor_principal_id=scenario.principal_id)
    barrier = asyncio.Barrier(2)

    async def assign() -> CompletedSynchronousOperationDTO:
        async with database.session() as session:
            service = create_project_grant_change_service(session)
            await barrier.wait()
            return await service.assign_use_only(
                access=access,
                context=request,
                command=AssignProjectUseOnlyGrantCommand(
                    project_id=scenario.project_id,
                    recipient_principal_id=recipient_id,
                    action_id=action_id,
                    expected_access_revision=0,
                ),
            )

    first, second = await asyncio.gather(assign(), assign())

    assert first.operation_id == second.operation_id
    assert sorted((first.created, second.created)) == [False, True]

    async with database.session() as session:
        grants = (
            await session.scalars(
                select(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == scenario.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id == recipient_id.value,
                    ProjectActionGrantRow.action == action_id.value,
                )
            )
        ).all()
        audit_events = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.project_id == scenario.project_id.value,
                    AccessAuditEventRow.affected_principal_id == recipient_id.value,
                    AccessAuditEventRow.action == action_id.value,
                )
            )
        ).all()
        reservations = (
            await session.scalars(
                select(IdempotencyReservationRow).where(
                    IdempotencyReservationRow.principal_id == scenario.principal_id.value,
                    IdempotencyReservationRow.project_id == scenario.project_id.value,
                    IdempotencyReservationRow.request_key == request.key.value,
                )
            )
        ).all()
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == scenario.project_id.value)
        )

    assert len(grants) == 1
    assert grants[0].can_grant is False
    assert len(audit_events) == 1
    assert audit_events[0].correlation_id == first.operation_id.value
    assert len(reservations) == 1
    assert reservations[0].operation_id == first.operation_id.value
    assert reservations[0].state is OperationReservationState.REPLAYABLE
    assert reservations[0].replay_kind is OperationReplayKind.SAFE_RESULT
    assert revision == 1


class MockPausedProjectGrantAuthorizer(ProjectGrantAuthorizer):
    """Pause after real locks, or expose the competing transaction for observation."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        authorized: asyncio.Event | None = None,
        release: asyncio.Event | None = None,
        pid_ready: asyncio.Future[int] | None = None,
    ) -> None:
        self._session = session
        self._delegate = ProjectGrantAuthorizationService(
            PostgresProjectGrantChangeFactsReader(session)
        )
        self._authorized = authorized
        self._release = release
        self._pid_ready = pid_ready

    @override
    async def require_authorization(
        self, *, access: AccessContextDTO, request: ProjectUseOnlyGrantAuthorizationRequestDTO
    ) -> ProjectGrantAuthorizationDTO:
        if self._pid_ready is not None:
            self._pid_ready.set_result(
                (
                    await self._session.execute(select(func.pg_backend_pid().cast(Integer)))
                ).scalar_one()
            )
        result = await self._delegate.require_authorization(access=access, request=request)
        if self._authorized is not None:
            self._authorized.set()
        if self._release is not None:
            await self._release.wait()
        return result


@pytest.mark.asyncio
async def test_competing_memberships_share_the_project_revision(database: Database) -> None:
    """Different membership aggregates cannot independently spend the same project revision."""
    bob, carol = PrincipalId(uuid4()), PrincipalId(uuid4())
    action = ActionId("create-access-groups")
    async with database.session() as session, session.begin():
        seed = await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=True, has_action_grant=False
        )
        session.add_all(
            [
                PrincipalRow(
                    id=principal.value,
                    organization_id=seed.organization_id.value,
                    kind=PrincipalKind.HUMAN,
                    status=PrincipalStatus.ACTIVE,
                    display_name=name,
                )
                for principal, name in ((bob, "Bob"), (carol, "Carol"))
            ]
        )
        await session.flush()
        session.add_all(
            [
                ProjectMembershipRow(
                    project_id=seed.project_id.value,
                    principal_id=principal.value,
                    organization_id=seed.organization_id.value,
                    principal_kind=PrincipalKind.HUMAN,
                )
                for principal in (bob, carol)
            ]
        )
        session.add(
            ProjectActionGrantRow(
                project_id=seed.project_id.value,
                recipient_principal_id=seed.principal_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action=action.value,
                can_grant=True,
            )
        )

    access = AccessContextDTO(seed.principal_id)
    authorized, release = asyncio.Event(), asyncio.Event()
    pid_ready = asyncio.get_running_loop().create_future()

    async def first_assignment() -> CompletedSynchronousOperationDTO:
        async with database.session() as session:
            authorizer = MockPausedProjectGrantAuthorizer(
                session, authorized=authorized, release=release
            )
            return await create_project_grant_change_service(
                session, authorizer=authorizer
            ).assign_use_only(
                access=access,
                command=AssignProjectUseOnlyGrantCommand(seed.project_id, bob, action, 0),
                context=OperationAdmissionContextDTO(
                    "POST", "/v1/projects/{project_id}/grants", IdempotencyKey("bob-change")
                ),
            )

    async def second_assignment() -> None:
        async with database.session() as session:
            authorizer = MockPausedProjectGrantAuthorizer(session, pid_ready=pid_ready)
            with pytest.raises(StaleRevisionError):
                await create_project_grant_change_service(
                    session, authorizer=authorizer
                ).assign_use_only(
                    access=access,
                    command=AssignProjectUseOnlyGrantCommand(seed.project_id, carol, action, 0),
                    context=OperationAdmissionContextDTO(
                        "POST", "/v1/projects/{project_id}/grants", IdempotencyKey("carol-change")
                    ),
                )
            assert not session.in_transaction()

    async with asyncio.TaskGroup() as tasks:
        first = tasks.create_task(first_assignment())
        async with asyncio.timeout(2):
            await authorized.wait()
        tasks.create_task(second_assignment())
        try:
            async with asyncio.timeout(2):
                pid = await pid_ready
                while True:
                    async with database.session() as observer:
                        blockers = await observer.scalar(
                            select(func.pg_blocking_pids(pid).cast(ARRAY(Integer)))
                        )
                    if blockers:
                        break
                    await asyncio.sleep(0.01)
        finally:
            release.set()

    async with database.session() as session:
        recipients = (
            await session.scalars(
                select(ProjectActionGrantRow.recipient_principal_id).where(
                    ProjectActionGrantRow.project_id == seed.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id.in_((bob.value, carol.value)),
                )
            )
        ).all()
        assert recipients == [bob.value]
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == seed.project_id.value)
            )
            == 1
        )
        audit = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.project_id == seed.project_id.value
                )
            )
        ).one()
        assert audit.affected_principal_id == bob.value
        assert audit.correlation_id == first.result().operation_id.value
        reservation = (
            await session.scalars(
                select(IdempotencyReservationRow).where(
                    IdempotencyReservationRow.project_id == seed.project_id.value
                )
            )
        ).one()
        assert reservation.operation_id == first.result().operation_id.value
        assert reservation.request_key == "bob-change"
