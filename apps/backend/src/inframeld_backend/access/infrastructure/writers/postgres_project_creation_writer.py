from typing import override
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.created_project_dto import CreatedProjectDTO
from inframeld_backend.access.application.protocols.project_creation_writer import (
    ProjectCreationWriter,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.policies.project_creation_policy import ProjectCreationPolicy
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_creation_operation_result_row import (
    ProjectCreationOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_name_reservation_row import (
    ProjectNameReservationRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    StaleRevisionError,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresProjectCreationWriter(ProjectCreationWriter):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def create(
        self, *, project: CreatedProjectDTO, expected_organization_revision: int
    ) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Creation persistence requires the active caller transaction.")
        actions = [action.value for action in project.initial_actions]
        if (
            project.access_revision != 1
            or project.metadata_revision != 0
            or tuple(actions) != ProjectCreationPolicy.INITIAL_ACTIONS
        ):
            raise RuntimeError("Creation persistence changed the fixed initial state.")
        reservation = await self._session.scalar(
            select(IdempotencyReservationRow.operation_id).where(
                IdempotencyReservationRow.operation_id == project.operation_id.value,
                IdempotencyReservationRow.organization_id == project.organization_id.value,
                IdempotencyReservationRow.project_id.is_(None),
                IdempotencyReservationRow.principal_id == project.creator_principal_id.value,
                IdempotencyReservationRow.method == "POST",
                IdempotencyReservationRow.requested_route == "/v1/projects",
                IdempotencyReservationRow.lookup_authority_family == "organization_action_use",
                IdempotencyReservationRow.lookup_action_id == "create-projects",
                IdempotencyReservationRow.state == OperationReservationState.IN_PROGRESS,
            )
        )
        if reservation is None:
            raise ConflictError("Creation has no matching original reservation.")
        revision = await self._session.scalar(
            select(OrganizationRow.access_revision).where(
                OrganizationRow.id == project.organization_id.value
            )
        )
        if revision != expected_organization_revision:
            raise StaleRevisionError()
        human = await self._session.scalar(
            select(PrincipalRow.id).where(
                PrincipalRow.id == project.creator_principal_id.value,
                PrincipalRow.organization_id == project.organization_id.value,
                PrincipalRow.kind == PrincipalKind.HUMAN,
                PrincipalRow.status == PrincipalStatus.ACTIVE,
            )
        )
        if human is None:
            raise ConflictError("The checked creator is no longer eligible.")

        row = ProjectRow(
            id=project.project_id.value,
            organization_id=project.organization_id.value,
            name=project.display_name,
            resource_name=project.name.value,
            status=ProjectStatus.ACTIVE,
        )
        self._session.add(row)
        await self._session.flush()
        if row.access_revision != 0 or row.metadata_revision != 0:
            raise RuntimeError("The new Project has no coherent initial revisions.")
        row.access_revision = project.access_revision
        allocated = await self._session.scalar(
            insert(ProjectNameReservationRow)
            .values(
                organization_id=project.organization_id.value,
                name=project.name.value,
                project_id=project.project_id.value,
                binding_revision=0,
                retired=False,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    ProjectNameReservationRow.organization_id,
                    ProjectNameReservationRow.name,
                ]
            )
            .returning(ProjectNameReservationRow.name)
        )
        if allocated is None:
            raise ConflictError("The requested Project name is unavailable.")
        self._session.add(
            ProjectMembershipRow(
                project_id=project.project_id.value,
                principal_id=human,
                organization_id=project.organization_id.value,
                principal_kind=PrincipalKind.HUMAN,
                assigned_by_principal_id=human,
            )
        )
        await self._session.flush()
        for action in actions:
            self._session.add(
                ProjectActionGrantRow(
                    project_id=project.project_id.value,
                    recipient_principal_id=human,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=action,
                    can_grant=True,
                    assigned_by_principal_id=human,
                )
            )
        self._session.add(
            ProjectCreationOperationResultRow(
                operation_id=project.operation_id.value,
                organization_id=project.organization_id.value,
                project_id=project.project_id.value,
                creator_principal_id=human,
                name=project.name.value,
                display_name=project.display_name,
                access_revision=project.access_revision,
                metadata_revision=project.metadata_revision,
                initial_actions=actions,
            )
        )
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=project.organization_id.value,
                project_id=project.project_id.value,
                actor_kind="human",
                actor_principal_id=human,
                affected_principal_id=human,
                event_type="project_created",
                target_kind="project",
                target_id=project.project_id.value,
                after_values={
                    "name": project.name.value,
                    "display_name": project.display_name,
                    "access_revision": 1,
                    "metadata_revision": 0,
                    "initial_actions": actions,
                },
                correlation_id=project.operation_id.value,
            )
        )
        await self._session.flush()
