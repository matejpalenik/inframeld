from typing import override

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.project_action_grant_change_result_dto import (
    ProjectActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.enums.project_action_grant_change_kind import (
    ProjectActionGrantChangeKind,
)
from inframeld_backend.access.application.protocols.project_action_grant_result_writer import (
    ProjectActionGrantResultWriter,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_operation_result_row import (
    ProjectActionGrantOperationResultRow,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresProjectActionGrantResultWriter(ProjectActionGrantResultWriter):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def save(
        self,
        result: ProjectActionGrantChangeResultDTO,
        *,
        before_revision: int,
        before_can_grant: bool | None,
    ) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Grant results require the active caller transaction.")
        if (
            type(before_revision) is not int
            or not 0 <= before_revision <= 2**63 - 1
            or type(result.access_revision) is not int
            or not 0 <= result.access_revision <= 2**63 - 1
        ):
            raise RuntimeError("The original grant revisions are invalid.")
        if (
            (before_can_grant is not None and type(before_can_grant) is not bool)
            or (result.can_grant is not None and type(result.can_grant) is not bool)
            or type(result.changed) is not bool
        ):
            raise RuntimeError("The original grant levels are invalid.")
        if (
            result.change_kind
            not in {ProjectActionGrantChangeKind.SET, ProjectActionGrantChangeKind.REMOVE}
            or (result.change_kind == ProjectActionGrantChangeKind.SET)
            != (result.can_grant is not None)
            or result.changed != (before_can_grant is not result.can_grant)
            or result.access_revision != before_revision + int(result.changed)
            or result.status_code
            != (
                201
                if result.change_kind == ProjectActionGrantChangeKind.SET
                and before_can_grant is None
                else 200
            )
        ):
            raise RuntimeError("The original grant outcome is incoherent.")
        parent = IdempotencyReservationRow
        route = f"/v1/projects/{result.project_id.value}/grants/{result.recipient_principal_id.value}/{result.action_id.value}"
        bound = await self._session.scalar(
            select(parent.operation_id).where(
                parent.operation_id == result.operation.operation_id.value,
                parent.organization_id == result.organization_id.value,
                parent.project_id == result.project_id.value,
                parent.principal_id == result.actor_principal_id.value,
                parent.method
                == ("PUT" if result.change_kind == ProjectActionGrantChangeKind.SET else "DELETE"),
                parent.requested_route == route,
                parent.lookup_authority_family == "project_grant_read",
                parent.lookup_action_id == result.action_id.value,
                parent.state == OperationReservationState.REPLAYABLE,
                parent.replay_kind == OperationReplayKind.SAFE_RESULT,
                parent.expires_at == result.operation.expires_at,
                parent.expires_at > func.clock_timestamp(),
            )
        )
        if bound is None:
            raise RuntimeError("The original grant result lost its completed reservation.")
        self._session.add(
            ProjectActionGrantOperationResultRow(
                operation_id=result.operation.operation_id.value,
                installation_id=result.installation_id.value,
                organization_id=result.organization_id.value,
                project_id=result.project_id.value,
                actor_principal_id=result.actor_principal_id.value,
                recipient_principal_id=result.recipient_principal_id.value,
                action_id=result.action_id.value,
                change_kind=result.change_kind.value,
                before_revision=before_revision,
                access_revision=result.access_revision,
                changed=result.changed,
                status_code=result.status_code,
                before_can_grant=before_can_grant,
                can_grant=result.can_grant,
            )
        )
        await self._session.flush()
