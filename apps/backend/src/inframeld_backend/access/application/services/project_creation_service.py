import asyncio
from typing import override
from uuid import uuid4

from inframeld_backend.access.application.commands.create_project_command import (
    CreateProjectCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.created_project_dto import CreatedProjectDTO
from inframeld_backend.access.application.dtos.project_creation_result_dto import (
    ProjectCreationResultDTO,
)
from inframeld_backend.access.application.protocols.project_creation_authorizer import (
    ProjectCreationAuthorizer,
)
from inframeld_backend.access.application.protocols.project_creation_result_reader import (
    ProjectCreationResultReader,
)
from inframeld_backend.access.application.protocols.project_creation_writer import (
    ProjectCreationWriter,
)
from inframeld_backend.access.application.protocols.project_creator import ProjectCreator
from inframeld_backend.access.application.services.project_creation_fingerprint_service import (
    ProjectCreationFingerprintService,
)
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.policies.project_creation_policy import ProjectCreationPolicy
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)


class ProjectCreationService(ProjectCreator):
    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        creation_authorizer: ProjectCreationAuthorizer,
        creation_writer: ProjectCreationWriter,
        creation_result_reader: ProjectCreationResultReader,
        operation_idempotency: OperationIdempotency,
        creation_fingerprint_service: ProjectCreationFingerprintService,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._creation_authorizer = creation_authorizer
        self._creation_writer = creation_writer
        self._creation_result_reader = creation_result_reader
        self._operation_idempotency = operation_idempotency
        self._creation_fingerprint_service = creation_fingerprint_service

    @override
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateProjectCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectCreationResultDTO:
        if context.method != "POST" or context.requested_route != "/v1/projects":
            raise RuntimeError("Project creation changed its original operation route.")
        fingerprint = self._creation_fingerprint_service.for_create(command)
        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                scope = await self._creation_authorizer.require_creation(
                    access=access, organization_id=command.organization_id
                )
                if scope.organization_id != command.organization_id or scope.project_id is not None:
                    raise RuntimeError("Creation authorization changed the requested scope.")

                operation = await self._operation_idempotency.reserve_or_recover(
                    context=context,
                    access=access,
                    authorization=scope,
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                    lookup_authority=OperationLookupAuthority(
                        OperationLookupAuthorityFamily.ORGANIZATION_ACTION_USE,
                        ActionId(OrganizationAction.CREATE_PROJECTS.value),
                    ),
                )
                actions = tuple(ActionId(value) for value in ProjectCreationPolicy.INITIAL_ACTIONS)
                if not isinstance(operation, NewOperationReservationDTO):
                    completed = self._require_safe_completed_operation(operation)
                    original = await self._creation_result_reader.original(
                        organization_id=scope.organization_id,
                        actor_id=access.actor_principal_id,
                        operation_id=completed.operation_id,
                    )
                    if (
                        original.operation_id != completed.operation_id
                        or original.organization_id != scope.organization_id
                        or original.creator_principal_id != access.actor_principal_id
                        or original.access_revision != 1
                        or original.metadata_revision != 0
                        or original.initial_actions != actions
                    ):
                        raise ConflictError("The original creation result is incoherent.")
                    return ProjectCreationResultDTO(original, completed)

                if command.expected_access_revision != scope.access_revision:
                    raise StaleRevisionError()
                project = CreatedProjectDTO(
                    operation.operation_id,
                    scope.organization_id,
                    ProjectId(uuid4()),
                    access.actor_principal_id,
                    command.name,
                    command.display_name.value,
                    1,
                    0,
                    actions,
                )
                await self._creation_writer.create(
                    project=project, expected_organization_revision=scope.access_revision
                )
                completed = self._require_safe_completed_operation(
                    await self._operation_idempotency.record_completed_result(
                        operation, replay_kind=OperationReplayKind.SAFE_RESULT
                    )
                )
                if completed.operation_id != operation.operation_id:
                    raise RuntimeError("Creation completion changed the original operation.")
                return ProjectCreationResultDTO(project, completed)
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @staticmethod
    def _require_safe_completed_operation(operation: object) -> CompletedSynchronousOperationDTO:
        """Reject saved outcomes that cannot safely reconstruct the original Project creation."""
        if (
            not isinstance(operation, CompletedSynchronousOperationDTO)
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
        ):
            raise ConflictError("Creation has no safe completed result.")
        return operation
