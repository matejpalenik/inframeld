"""Save a new use-only project grant and its Access change records."""

from typing import final, override
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.protocols.project_grant_change_writer import (
    ProjectGrantChangeWriter,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import (
    AccessAuditEventRow,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@final
class PostgresProjectGrantChangeWriter(ProjectGrantChangeWriter):
    """Use the caller's session - the caller owns commit or rollback."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def create_use_only(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_principal_id: PrincipalId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
        expected_access_revision: int,
        operation_id: OperationId,
    ) -> None:
        revision_update = (
            update(ProjectRow)
            .where(
                ProjectRow.id == project_id.value,
                ProjectRow.organization_id == organization_id.value,
                ProjectRow.status == ProjectStatus.ACTIVE,
                ProjectRow.access_revision == expected_access_revision,
            )
            .values(access_revision=ProjectRow.access_revision + 1)
            .returning(ProjectRow.id)
        )
        updated_project_id = (await self._session.execute(revision_update)).scalar_one_or_none()

        if updated_project_id is None:
            raise ConflictError("The project access revision has changed.")

        grant_insert = (
            insert(ProjectActionGrantRow)
            .values(
                project_id=project_id.value,
                recipient_principal_id=recipient_principal_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action=action_id.value,
                can_grant=False,
                assigned_by_principal_id=actor_principal_id.value,
            )
            .on_conflict_do_nothing(constraint="pk_project_action_grants")
            .returning(ProjectActionGrantRow.project_id)
        )
        inserted_project_id = (await self._session.execute(grant_insert)).scalar_one_or_none()

        if inserted_project_id is None:
            raise ConflictError("This project action grant already exists.")

        after_values: dict[str, object] = {"can_grant": False}
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=organization_id.value,
                project_id=project_id.value,
                actor_kind=PrincipalKind.HUMAN.value,
                actor_principal_id=actor_principal_id.value,
                affected_principal_id=recipient_principal_id.value,
                event_type="project_action_grant_assigned",
                target_kind="project",
                target_id=project_id.value,
                action=action_id.value,
                after_values=after_values,
                correlation_id=operation_id.value,
            )
        )
        await self._session.flush()
