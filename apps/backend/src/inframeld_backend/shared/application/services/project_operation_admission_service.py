"""Admit project operations through current authorization and reservation."""

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.protocols.action_authorizer import ActionAuthorizer
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_result_dto import (
    OperationReservationResultDTO,
)
from inframeld_backend.shared.application.dtos.project_operation_admission_request_dto import (
    ProjectOperationAdmissionRequestDTO,
)
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    IdempotencyInProgressError,
)
from inframeld_backend.shared.application.protocols.operation_reservation_writer import (
    OperationReservationWriter,
)


class ProjectOperationAdmissionService:
    """Check current project authority before finding or creating an operation."""

    def __init__(
        self, authorizer: ActionAuthorizer, reservations: OperationReservationWriter
    ) -> None:
        self._authorizer = authorizer
        self._reservations = reservations

    async def reserve(
        self,
        *,
        access: AccessContextDTO,
        action_id: ActionId,
        request: ProjectOperationAdmissionRequestDTO,
    ) -> OperationReservationResultDTO:
        """Authorize every call, then reserve under the verified principal and scope."""
        organization_id = await self._authorizer.require_action(
            access=access,
            action_id=action_id,
            target=ProjectActionTargetDTO(project_id=request.project_id),
        )

        result = await self._reservations.reserve(
            OperationReservationRequestDTO(
                principal_id=access.actor_principal_id,
                organization_id=organization_id,
                project_id=request.project_id,
                method=request.method,
                requested_route=request.requested_route,
                key=request.key,
                fingerprint=request.fingerprint,
            )
        )

        if not result.created and result.state is OperationReservationState.IN_PROGRESS:
            raise IdempotencyInProgressError(
                operation_id=result.operation_id, retry_after_seconds=3
            )

        return result
