from typing import override

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.delete_access_group_command import (
    DeleteAccessGroupCommand,
)
from inframeld_backend.access.application.dtos.deleted_access_group_dto import DeletedAccessGroupDTO
from inframeld_backend.access.application.protocols.access_group_deletion_result_reader import (
    AccessGroupDeletionResultReader,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.access_group_deletion_result_row import (
    AccessGroupDeletionResultRow,
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
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresAccessGroupDeletionResultReader(AccessGroupDeletionResultReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def original(
        self,
        *,
        organization_id: OrganizationId,
        actor_id: PrincipalId,
        command: DeleteAccessGroupCommand,
        operation_id: OperationId,
    ) -> DeletedAccessGroupDTO:
        try:
            if not self._session.in_transaction() or not self._session.is_active:
                raise RuntimeError("Group deletion replay requires the active caller transaction.")
            native, saved = IdempotencyReservationRow, AccessGroupDeletionResultRow
            route = (
                f"/v1/projects/{command.project_id.value}/access-groups/{command.group_id.value}"
            )
            row = await self._session.scalar(
                select(saved)
                .join(native, native.operation_id == saved.operation_id)
                .where(
                    saved.operation_id == operation_id.value,
                    saved.organization_id == organization_id.value,
                    saved.project_id == command.project_id.value,
                    saved.group_id == command.group_id.value,
                    saved.actor_principal_id == actor_id.value,
                    saved.before_revision == command.expected_access_revision,
                    native.organization_id == saved.organization_id,
                    native.project_id == saved.project_id,
                    native.principal_id == saved.actor_principal_id,
                    native.method == "DELETE",
                    native.requested_route == route,
                    native.lookup_authority_family == "access_group_deletion",
                    native.lookup_action_id == "delete-access-group",
                    native.state == OperationReservationState.REPLAYABLE,
                    native.replay_kind == OperationReplayKind.SAFE_RESULT,
                    native.expires_at > func.clock_timestamp(),
                )
                .execution_options(populate_existing=True, autoflush=False)
            )
            if row is None:
                raise ConflictError("The original group deletion receipt is unavailable.")
            return DeletedAccessGroupDTO(
                operation_id,
                organization_id,
                command.project_id,
                command.group_id,
                actor_id,
                row.access_revision,
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
