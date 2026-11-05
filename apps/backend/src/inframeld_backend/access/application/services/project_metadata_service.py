from typing import override

from inframeld_backend.access.application.commands.update_project_metadata_command import (
    UpdateProjectMetadataCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_metadata_change_result_dto import (
    ProjectMetadataChangeResultDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_dto import ProjectMetadataDTO
from inframeld_backend.access.application.protocols.project_metadata_authorizer import (
    ProjectMetadataAuthorizer,
)
from inframeld_backend.access.application.protocols.project_metadata_changer import (
    ProjectMetadataChanger,
)
from inframeld_backend.access.application.protocols.project_metadata_reader import (
    ProjectMetadataReader,
)
from inframeld_backend.access.application.protocols.project_metadata_repository import (
    ProjectMetadataRepository,
)
from inframeld_backend.access.application.queries.get_project_metadata_query import (
    GetProjectMetadataQuery,
)
from inframeld_backend.access.application.services.project_metadata_fingerprint_service import (
    ProjectMetadataFingerprintService,
)
from inframeld_backend.access.domain.entities.project_metadata import ProjectMetadata
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.errors.project_metadata_errors import (
    ProjectMetadataStaleRevisionError,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
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
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)


class ProjectMetadataService(ProjectMetadataReader, ProjectMetadataChanger):
    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        metadata_authorizer: ProjectMetadataAuthorizer,
        operation_idempotency: OperationIdempotency,
        metadata_repository: ProjectMetadataRepository,
        metadata_fingerprint_service: ProjectMetadataFingerprintService,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._metadata_authorizer = metadata_authorizer
        self._operation_idempotency = operation_idempotency
        self._metadata_repository = metadata_repository
        self._metadata_fingerprint_service = metadata_fingerprint_service

    @override
    async def get(
        self, *, access: AccessContextDTO, query: GetProjectMetadataQuery
    ) -> ProjectMetadataDTO:
        async with self._transaction_manager.begin():
            scope = await self._metadata_authorizer.require_read(
                access=access, project_id=query.project_id
            )
            if scope.project_id != query.project_id:
                raise RuntimeError("Metadata authorization changed the Project.")
            metadata = await self._metadata_repository.get(
                organization_id=scope.organization_id, project_id=scope.project_id
            )
            self._require_scope(metadata, scope.organization_id, scope.project_id)
            return self._dto(metadata)

    @override
    async def update(
        self,
        *,
        access: AccessContextDTO,
        command: UpdateProjectMetadataCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectMetadataChangeResultDTO:
        fingerprint = self._metadata_fingerprint_service.for_update(command)
        async with self._transaction_manager.begin():
            scope = await self._metadata_authorizer.require_change(
                access=access, project_id=command.project_id
            )
            if scope.project_id != command.project_id:
                raise RuntimeError("Metadata authorization changed the Project.")
            operation = await self._operation_idempotency.reserve_or_recover(
                context=context,
                access=access,
                authorization=scope,
                fingerprint=fingerprint,
                expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                lookup_authority=OperationLookupAuthority(
                    OperationLookupAuthorityFamily.PROJECT_ACTION_USE,
                    ActionId(ProjectAction.EDIT_PROJECT_METADATA.value),
                ),
            )
            if not isinstance(operation, NewOperationReservationDTO):
                completed = self._require_safe_completed_operation(operation)
                original = await self._metadata_repository.original(
                    organization_id=scope.organization_id,
                    project_id=scope.project_id,
                    operation_id=completed.operation_id,
                )
                if (original.organization_id, original.project_id) != (
                    scope.organization_id,
                    scope.project_id,
                ):
                    raise RuntimeError("The original result changed its Project binding.")
                return ProjectMetadataChangeResultDTO(original, completed)

            metadata = await self._metadata_repository.get(
                organization_id=scope.organization_id, project_id=scope.project_id
            )
            self._require_scope(metadata, scope.organization_id, scope.project_id)
            try:
                metadata.change(
                    expected_revision=command.expected_metadata_revision,
                    name=command.name,
                    display_name=command.display_name,
                )
            except ProjectMetadataStaleRevisionError as error:
                raise StaleRevisionError() from error

            await self._metadata_repository.save(
                metadata,
                expected_revision=command.expected_metadata_revision,
                actor_id=access.actor_principal_id,
                operation_id=operation.operation_id,
            )
            completed = self._require_safe_completed_operation(
                await self._operation_idempotency.record_completed_result(
                    operation, replay_kind=OperationReplayKind.SAFE_RESULT
                )
            )
            return ProjectMetadataChangeResultDTO(self._dto(metadata), completed)

    @staticmethod
    def _dto(metadata: ProjectMetadata) -> ProjectMetadataDTO:
        return ProjectMetadataDTO(
            metadata.organization_id,
            metadata.project_id,
            metadata.name,
            metadata.display_name,
            metadata.revision,
        )

    @staticmethod
    def _require_scope(
        metadata: ProjectMetadata, organization_id: OrganizationId, project_id: ProjectId
    ) -> None:
        """Reject an authorizer result that substituted another Project."""
        if (metadata.organization_id, metadata.project_id) != (organization_id, project_id):
            raise RuntimeError("The loaded metadata changed its authorized scope.")

    @staticmethod
    def _require_safe_completed_operation(operation: object) -> CompletedSynchronousOperationDTO:
        """Require the safe synchronous outcome supported by metadata retries."""
        if (
            not isinstance(operation, CompletedSynchronousOperationDTO)
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
        ):
            raise ConflictError("The metadata operation has no safe completed outcome.")
        return operation
