from typing import override

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.project_membership_change_facts_dto import (
    ProjectMembershipChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.project_membership_change_result_dto import (
    ProjectMembershipChangeResultDTO,
)
from inframeld_backend.access.application.enums.project_membership_change_kind import (
    ProjectMembershipChangeKind,
)
from inframeld_backend.access.application.protocols.project_membership_change_result_reader import (
    ProjectMembershipChangeResultReader,
)
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.project_membership_operation_result_row import (
    ProjectMembershipOperationResultRow,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresProjectMembershipChangeResultReader(ProjectMembershipChangeResultReader):
    """Recover original membership meaning only under exact live reservation bindings."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def load_original_membership_result(
        self,
        *,
        facts: ProjectMembershipChangeFactsDTO,
        principal_id: PrincipalId,
        change_kind: ProjectMembershipChangeKind,
        operation: CompletedSynchronousOperationDTO,
    ) -> ProjectMembershipChangeResultDTO:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Membership replay requires the active caller transaction.")
        if operation.replay_kind is not OperationReplayKind.SAFE_RESULT:
            raise ConflictError("The original membership result is unavailable.")
        result, parent = ProjectMembershipOperationResultRow, IdempotencyReservationRow
        method = change_kind.http_method
        route = f"/v1/projects/{facts.project_id.value}/members/{principal_id.value}"
        try:
            row = await self._session.scalar(
                select(result)
                .join(parent, parent.operation_id == result.operation_id)
                .where(
                    result.operation_id == operation.operation_id.value,
                    result.installation_id == facts.installation_id.value,
                    result.organization_id == facts.organization_id.value,
                    result.project_id == facts.project_id.value,
                    result.actor_principal_id == facts.action.principal.id.value,
                    result.principal_id == principal_id.value,
                    result.change_kind == change_kind.value,
                    parent.principal_id == result.actor_principal_id,
                    parent.organization_id == result.organization_id,
                    parent.project_id == result.project_id,
                    parent.method == method,
                    parent.requested_route == route,
                    parent.lookup_authority_family == "project_action_use",
                    parent.lookup_action_id == ProjectAction.MANAGE_PROJECT_MEMBERS.value,
                    parent.state == OperationReservationState.REPLAYABLE,
                    parent.replay_kind == OperationReplayKind.SAFE_RESULT,
                    parent.expires_at == operation.expires_at,
                    parent.expires_at > func.clock_timestamp(),
                )
                .execution_options(populate_existing=True, autoflush=False)
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        if row is None:
            raise ConflictError("The original membership result is unavailable.")
        if (
            row.before_revision < 0
            or row.access_revision != row.before_revision + int(row.changed)
            or row.status_code != change_kind.success_status(changed=row.changed)
        ):
            raise ConflictError("The original membership result is incoherent.")
        return ProjectMembershipChangeResultDTO(
            installation_id=facts.installation_id,
            organization_id=facts.organization_id,
            project_id=facts.project_id,
            actor_principal_id=facts.action.principal.id,
            principal_id=principal_id,
            change_kind=change_kind,
            access_revision=row.access_revision,
            changed=row.changed,
            status_code=row.status_code,
            operation=operation,
        )
