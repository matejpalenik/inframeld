from typing import override

from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_use_only_grant_authorization_request_dto import (
    ProjectUseOnlyGrantAuthorizationRequestDTO,
)
from inframeld_backend.access.application.protocols.project_grant_authorizer import (
    ProjectGrantAuthorizer,
)
from inframeld_backend.access.application.protocols.project_grant_changer import ProjectGrantChanger
from inframeld_backend.access.application.protocols.project_membership_repository import (
    ProjectMembershipRepository,
)
from inframeld_backend.access.application.services.project_grant_change_fingerprint_service import (
    ProjectGrantChangeFingerprintService,
)
from inframeld_backend.access.domain.errors.project_grant_errors import (
    ProjectGrantAlreadyExistsError,
)
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)


class ProjectGrantChangeService(ProjectGrantChanger):
    def __init__(
        self,
        transaction_manager: TransactionManager,
        project_grant_authorizer: ProjectGrantAuthorizer,
        operation_idempotency: OperationIdempotency,
        membership_repository: ProjectMembershipRepository,
        project_grant_change_fingerprint_service: ProjectGrantChangeFingerprintService,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._project_grant_authorizer = project_grant_authorizer
        self._operation_idempotency = operation_idempotency
        self._membership_repository = membership_repository
        self._project_grant_change_fingerprint_service = project_grant_change_fingerprint_service

    @override
    async def assign_use_only(
        self,
        *,
        access: AccessContextDTO,
        command: AssignProjectUseOnlyGrantCommand,
        context: IdempotencyContextDTO,
    ) -> CompletedSynchronousOperationDTO:
        fingerprint = self._project_grant_change_fingerprint_service.for_assign_use_only(command)

        async with self._transaction_manager.begin():
            authorization = await self._project_grant_authorizer.require_authorization(
                access=access,
                request=ProjectUseOnlyGrantAuthorizationRequestDTO(
                    project_id=command.project_id,
                    recipient_principal_id=command.recipient_principal_id,
                    action_id=command.action_id,
                ),
            )

            if authorization.project_id != command.project_id:
                raise RuntimeError("Authorization returned a different project than requested.")

            operation = await self._operation_idempotency.reserve_or_recover(
                context=context,
                access=access,
                authorization=authorization,
                fingerprint=fingerprint,
                expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                lookup_authority=OperationLookupAuthority(
                    OperationLookupAuthorityFamily.PROJECT_GRANT_READ, command.action_id
                ),
            )

            if not isinstance(operation, NewOperationReservationDTO):
                return self._require_completed_result(operation)

            # A replay keeps its original revision. Only new work checks current state.
            if authorization.project_access_revision != command.expected_access_revision:
                raise StaleRevisionError()

            membership = await self._membership_repository.get(
                organization_id=authorization.organization_id,
                project_id=authorization.project_id,
                principal_id=command.recipient_principal_id,
            )
            if (
                membership.organization_id != authorization.organization_id
                or membership.project_id != authorization.project_id
                or membership.principal_id != command.recipient_principal_id
            ):
                raise RuntimeError(
                    "The loaded membership does not match the authorized assignment."
                )

            try:
                membership.assign_use_only_grant(
                    action_id=command.action_id,
                    assigned_by_principal_id=access.actor_principal_id,
                )
            except ProjectGrantAlreadyExistsError as error:
                raise ConflictError("This project action grant already exists.") from error

            await self._membership_repository.save(
                membership,
                expected_project_access_revision=authorization.project_access_revision,
                operation_id=operation.operation_id,
            )
            completed = await self._operation_idempotency.record_completed_result(
                operation, replay_kind=OperationReplayKind.SAFE_RESULT
            )
            return self._require_completed_result(completed)

    @staticmethod
    def _require_completed_result(
        operation: CompletedSynchronousOperationDTO
        | AcceptedAsyncOperationDTO
        | RecoveryRequiredOperationDTO,
    ) -> CompletedSynchronousOperationDTO:
        if (
            not isinstance(operation, CompletedSynchronousOperationDTO)
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
        ):
            raise ConflictError("The grant operation has no completed replay outcome.")
        return operation
