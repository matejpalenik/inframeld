from typing import override

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.created_access_group_dto import (
    CreatedAccessGroupDTO,
)
from inframeld_backend.access.application.protocols.access_group_creation_result_reader import (
    AccessGroupCreationResultReader,
)
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.access_group_creation_result_row import (
    AccessGroupCreationResultRow,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresAccessGroupCreationResultReader(AccessGroupCreationResultReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def original(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_id: PrincipalId,
        operation_id: OperationId,
    ) -> CreatedAccessGroupDTO:
        try:
            if not self._session.in_transaction() or not self._session.is_active:
                raise RuntimeError("Group replay requires the active caller transaction.")
            parent, result = IdempotencyReservationRow, AccessGroupCreationResultRow
            row = await self._session.scalar(
                select(result)
                .join(parent, parent.operation_id == result.operation_id)
                .where(
                    result.operation_id == operation_id.value,
                    result.organization_id == organization_id.value,
                    result.project_id == project_id.value,
                    result.actor_principal_id == actor_id.value,
                    parent.organization_id == result.organization_id,
                    parent.project_id == result.project_id,
                    parent.principal_id == result.actor_principal_id,
                    parent.method == "POST",
                    parent.requested_route == f"/v1/projects/{project_id.value}/access-groups",
                    parent.lookup_authority_family == "project_action_use",
                    parent.lookup_action_id == ProjectAction.CREATE_ACCESS_GROUPS.value,
                    parent.state == OperationReservationState.REPLAYABLE,
                    parent.replay_kind == OperationReplayKind.SAFE_RESULT,
                    parent.expires_at.is_not(None),
                    parent.expires_at > func.clock_timestamp(),
                )
                .execution_options(populate_existing=True, autoflush=False)
            )
            if row is None:
                raise ConflictError("The original group creation result is unavailable.")
            if row.access_revision - row.before_revision != 1:
                raise ConflictError("The original group creation result is incoherent.")
            try:
                RevisionValidation.require(row.before_revision)
                RevisionValidation.require(row.access_revision)
                return CreatedAccessGroupDTO(
                    operation_id,
                    organization_id,
                    project_id,
                    AccessGroupId(row.group_id),
                    actor_id,
                    ResourceName(row.name),
                    row.display_name,
                    row.access_revision,
                )
            except (ValueError, TypeError):
                raise ConflictError("The original group creation result is incoherent.") from None
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
