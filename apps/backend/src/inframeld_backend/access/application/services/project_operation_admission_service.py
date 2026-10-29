"""Admit project operations through current authorization and shared idempotency."""

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
    ProjectActionAuthorizationRequestDTO,
)
from inframeld_backend.access.application.dtos.project_operation_admission_request_dto import (
    ProjectOperationAdmissionRequestDTO,
)
from inframeld_backend.access.application.protocols.action_authorizer import ActionAuthorizer
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)


class ProjectOperationAdmissionService:
    """Authorize admission before sharing retry decisions in the caller's transaction."""

    def __init__(self, authorizer: ActionAuthorizer, idempotency: OperationIdempotency) -> None:
        self._authorizer = authorizer
        self._idempotency = idempotency

    async def reserve(
        self,
        *,
        access: AccessContextDTO,
        action_id: ActionId,
        request: ProjectOperationAdmissionRequestDTO,
        expected_replay_kind: OperationReplayKind,
    ) -> (
        NewOperationReservationDTO
        | CompletedSynchronousOperationDTO
        | AcceptedAsyncOperationDTO
        | RecoveryRequiredOperationDTO
    ):
        authorization = await self._authorizer.require_authorization(
            access=access,
            request=ProjectActionAuthorizationRequestDTO(
                project_id=request.project_id,
                action_id=action_id,
            ),
        )
        if authorization.project_id != request.project_id:
            raise RuntimeError("Authorization returned a different project than requested.")

        return await self._idempotency.find_or_reserve(
            context=OperationAdmissionContextDTO(
                method=request.method,
                requested_route=request.requested_route,
                key=request.key,
            ),
            access=access,
            authorization=authorization,
            fingerprint=request.fingerprint,
            expected_replay_kind=expected_replay_kind,
            lookup_authority=OperationLookupAuthority(
                OperationLookupAuthorityFamily.PROJECT_ACTION_USE, action_id
            ),
        )
