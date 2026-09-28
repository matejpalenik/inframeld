"""Verify that a project grant change saves its current and historical records."""

import asyncio
import os
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import select
from tests.support.access_scenarios import MockAccessScenarios

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.services.project_grant_change_fingerprint_service import (
    ProjectGrantChangeFingerprintService,
)
from inframeld_backend.access.application.services.project_grant_change_service import (
    ProjectGrantChangeService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
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
from inframeld_backend.access.infrastructure.writers.postgres_project_grant_change_writer import (
    PostgresProjectGrantChangeWriter,
)
from inframeld_backend.shared.application.dtos.operation_reservation_result_dto import (
    OperationReservationResultDTO,
)
from inframeld_backend.shared.application.dtos.project_operation_admission_request_dto import (
    ProjectOperationAdmissionRequestDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    IdempotencyKeyReusedError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
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

    request = ProjectOperationAdmissionRequestDTO(
        project_id=scenario.project_id,
        method="POST",
        requested_route="/v1/projects/{project_id}/grants",
        key=IdempotencyKey("grant-bob-1"),
        fingerprint=b"\x01" * 32,
    )

    async with database.session() as session, session.begin():
        service = ProjectGrantChangeService(
            PostgresProjectGrantChangeFactsReader(session),
            PostgresOperationReservationWriter(session),
            PostgresProjectGrantChangeWriter(session),
        )
        await service.assign_use_only(
            access=AccessContextDTO(actor_principal_id=scenario.principal_id),
            request=request,
            recipient_principal_id=recipient_id,
            action_id=action_id,
            expected_access_revision=0,
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

    assert len(reservations) == 1
    assert reservations[0].organization_id == scenario.organization_id.value
    assert reservations[0].state is OperationReservationState.REPLAYABLE
    assert reservations[0].replay_kind is OperationReplayKind.SAFE_RESULT


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

    request = ProjectOperationAdmissionRequestDTO(
        project_id=scenario.project_id,
        method="POST",
        requested_route="/v1/projects/{project_id}/grants",
        key=IdempotencyKey("grant-bob-replay-1"),
        fingerprint=b"\x02" * 32,
    )
    access = AccessContextDTO(actor_principal_id=scenario.principal_id)

    async with database.session() as session, session.begin():
        service = ProjectGrantChangeService(
            PostgresProjectGrantChangeFactsReader(session),
            PostgresOperationReservationWriter(session),
            PostgresProjectGrantChangeWriter(session),
        )
        first_result = await service.assign_use_only(
            access=access,
            request=request,
            recipient_principal_id=recipient_id,
            action_id=action_id,
            expected_access_revision=0,
        )

    # The first transaction has committed, but the caller repeats its old request.
    async with database.session() as session, session.begin():
        service = ProjectGrantChangeService(
            PostgresProjectGrantChangeFactsReader(session),
            PostgresOperationReservationWriter(session),
            PostgresProjectGrantChangeWriter(session),
        )
        replay_result = await service.assign_use_only(
            access=access,
            request=request,
            recipient_principal_id=recipient_id,
            action_id=action_id,
            expected_access_revision=0,
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
    assert replay_result.state is OperationReservationState.REPLAYABLE
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

    request = ProjectOperationAdmissionRequestDTO(
        project_id=scenario.project_id,
        method="POST",
        requested_route="/v1/projects/{project_id}/grants",
        key=IdempotencyKey("grant-bob-original"),
        fingerprint=b"\x03" * 32,
    )
    access = AccessContextDTO(actor_principal_id=scenario.principal_id)

    async with database.session() as session, session.begin():
        service = ProjectGrantChangeService(
            PostgresProjectGrantChangeFactsReader(session),
            PostgresOperationReservationWriter(session),
            PostgresProjectGrantChangeWriter(session),
        )
        await service.assign_use_only(
            access=access,
            request=request,
            recipient_principal_id=recipient_id,
            action_id=action_id,
            expected_access_revision=0,
        )

    # This key represents a new command, unlike a retry of the original key.
    stale_request = replace(
        request,
        key=IdempotencyKey("grant-bob-new-command"),
    )

    # The exception must escape session.begin() so its reservation rolls back.
    with pytest.raises(StaleRevisionError):
        async with database.session() as session, session.begin():
            service = ProjectGrantChangeService(
                PostgresProjectGrantChangeFactsReader(session),
                PostgresOperationReservationWriter(session),
                PostgresProjectGrantChangeWriter(session),
            )
            await service.assign_use_only(
                access=access,
                request=stale_request,
                recipient_principal_id=recipient_id,
                action_id=action_id,
                expected_access_revision=0,
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

    fingerprints = ProjectGrantChangeFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    )
    request = ProjectOperationAdmissionRequestDTO(
        project_id=scenario.project_id,
        method="POST",
        requested_route="/v1/projects/{project_id}/grants",
        key=IdempotencyKey("grant-recipient-1"),
        fingerprint=fingerprints.for_assign_use_only(
            project_id=scenario.project_id,
            recipient_principal_id=bob_id,
            action_id=action_id,
            expected_access_revision=0,
        ),
    )
    access = AccessContextDTO(actor_principal_id=scenario.principal_id)

    async with database.session() as session, session.begin():
        service = ProjectGrantChangeService(
            PostgresProjectGrantChangeFactsReader(session),
            PostgresOperationReservationWriter(session),
            PostgresProjectGrantChangeWriter(session),
        )
        await service.assign_use_only(
            access=access,
            request=request,
            recipient_principal_id=bob_id,
            action_id=action_id,
            expected_access_revision=0,
        )

    changed_request = replace(
        request,
        fingerprint=fingerprints.for_assign_use_only(
            project_id=scenario.project_id,
            recipient_principal_id=carol_id,
            action_id=action_id,
            expected_access_revision=0,
        ),
    )

    with pytest.raises(IdempotencyKeyReusedError):
        async with database.session() as session, session.begin():
            service = ProjectGrantChangeService(
                PostgresProjectGrantChangeFactsReader(session),
                PostgresOperationReservationWriter(session),
                PostgresProjectGrantChangeWriter(session),
            )
            await service.assign_use_only(
                access=access,
                request=changed_request,
                recipient_principal_id=carol_id,
                action_id=action_id,
                expected_access_revision=0,
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

    fingerprints = ProjectGrantChangeFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    )
    request = ProjectOperationAdmissionRequestDTO(
        project_id=scenario.project_id,
        method="POST",
        requested_route="/v1/projects/{project_id}/grants",
        key=IdempotencyKey("grant-bob-concurrent-1"),
        fingerprint=fingerprints.for_assign_use_only(
            project_id=scenario.project_id,
            recipient_principal_id=recipient_id,
            action_id=action_id,
            expected_access_revision=0,
        ),
    )
    access = AccessContextDTO(actor_principal_id=scenario.principal_id)
    barrier = asyncio.Barrier(2)

    async def assign() -> OperationReservationResultDTO:
        async with database.session() as session, session.begin():
            service = ProjectGrantChangeService(
                PostgresProjectGrantChangeFactsReader(session),
                PostgresOperationReservationWriter(session),
                PostgresProjectGrantChangeWriter(session),
            )
            await barrier.wait()
            return await service.assign_use_only(
                access=access,
                request=request,
                recipient_principal_id=recipient_id,
                action_id=action_id,
                expected_access_revision=0,
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
