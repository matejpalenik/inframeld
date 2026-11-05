from typing import override

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.created_project_dto import CreatedProjectDTO
from inframeld_backend.access.application.protocols.project_creation_result_reader import (
    ProjectCreationResultReader,
)
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.policies.project_creation_policy import ProjectCreationPolicy
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.project_creation_operation_result_row import (
    ProjectCreationOperationResultRow,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresProjectCreationResultReader(ProjectCreationResultReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def original(
        self, *, organization_id: OrganizationId, actor_id: PrincipalId, operation_id: OperationId
    ) -> CreatedProjectDTO:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Creation replay requires the active caller transaction.")
        parent = IdempotencyReservationRow
        result = ProjectCreationOperationResultRow
        row = await self._session.scalar(
            select(result)
            .join(parent, parent.operation_id == result.operation_id)
            .where(
                result.operation_id == operation_id.value,
                result.organization_id == organization_id.value,
                result.creator_principal_id == actor_id.value,
                parent.organization_id == result.organization_id,
                parent.principal_id == result.creator_principal_id,
                parent.project_id.is_(None),
                parent.method == "POST",
                parent.requested_route == "/v1/projects",
                parent.lookup_authority_family == "organization_action_use",
                parent.lookup_action_id == OrganizationAction.CREATE_PROJECTS.value,
                parent.state == OperationReservationState.REPLAYABLE,
                parent.replay_kind == OperationReplayKind.SAFE_RESULT,
                parent.expires_at.is_not(None),
                parent.expires_at > func.clock_timestamp(),
            )
            .execution_options(populate_existing=True, autoflush=False)
        )
        if row is None:
            raise ConflictError("The original creation result is unavailable.")
        if (
            row.access_revision != 1
            or row.metadata_revision != 0
            or tuple(row.initial_actions) != ProjectCreationPolicy.INITIAL_ACTIONS
        ):
            raise ConflictError("The original creation result is incoherent.")
        try:
            return CreatedProjectDTO(
                operation_id,
                organization_id,
                ProjectId(row.project_id),
                actor_id,
                ResourceName(row.name),
                row.display_name,
                row.access_revision,
                row.metadata_revision,
                tuple(ActionId(action) for action in row.initial_actions),
            )
        except (ValueError, TypeError):
            raise ConflictError("The original creation result is incoherent.") from None
