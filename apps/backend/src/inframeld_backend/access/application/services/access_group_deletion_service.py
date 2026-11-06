import asyncio
from json import dumps
from typing import override

from inframeld_backend.access.application.commands.delete_access_group_command import (
    DeleteAccessGroupCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_deletion_result_dto import (
    AccessGroupDeletionResultDTO,
)
from inframeld_backend.access.application.dtos.deleted_access_group_dto import DeletedAccessGroupDTO
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.protocols.access_group_deleter import AccessGroupDeleter
from inframeld_backend.access.application.protocols.access_group_deletion_facts_reader import (
    AccessGroupDeletionFactsReader,
)
from inframeld_backend.access.application.protocols.access_group_deletion_result_reader import (
    AccessGroupDeletionResultReader,
)
from inframeld_backend.access.application.protocols.access_group_deletion_writer import (
    AccessGroupDeletionWriter,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.deletion_status_binding_writer import (
    DeletionStatusBindingWriter,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class AccessGroupDeletionService(AccessGroupDeleter):
    """Delete an unused group atomically with its original receipt and retained completion."""

    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        group_deletion_facts_reader: AccessGroupDeletionFactsReader,
        group_deletion_writer: AccessGroupDeletionWriter,
        group_deletion_result_reader: AccessGroupDeletionResultReader,
        operation_idempotency: OperationIdempotency,
        request_fingerprint_service: RequestFingerprintService,
        deletion_status_binding_writer: DeletionStatusBindingWriter,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._group_deletion_facts_reader = group_deletion_facts_reader
        self._group_deletion_writer = group_deletion_writer
        self._group_deletion_result_reader = group_deletion_result_reader
        self._operation_idempotency = operation_idempotency
        self._request_fingerprint_service = request_fingerprint_service
        self._deletion_status_binding_writer = deletion_status_binding_writer

    @override
    async def delete(
        self,
        *,
        access: AccessContextDTO,
        command: DeleteAccessGroupCommand,
        context: IdempotencyContextDTO,
        request_id: RequestId,
    ) -> AccessGroupDeletionResultDTO:
        route = f"/v1/projects/{command.project_id.value}/access-groups/{command.group_id.value}"
        if context.method != "DELETE" or context.requested_route != route:
            raise RuntimeError("Group deletion changed its original method or route.")
        authority = OperationLookupAuthority(
            OperationLookupAuthorityFamily.ACCESS_GROUP_DELETION, ActionId("delete-access-group")
        )
        fingerprint = self._request_fingerprint_service.fingerprint(
            purpose="access.group.delete:v1",
            canonical_request=dumps(
                {
                    "projectId": str(command.project_id.value),
                    "accessGroupId": str(command.group_id.value),
                    "expectedAccessRevision": command.expected_access_revision,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode(),
        )
        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = await self._group_deletion_facts_reader.lock_for_deletion(
                    access=access, project_id=command.project_id, group_id=command.group_id
                )
                if facts is None:
                    raise ResourceNotFoundError()
                group = facts.group
                if (
                    group.project_id != command.project_id
                    or group.group_id != command.group_id
                    or facts.action.principal.id != access.actor_principal_id
                    or facts.action.principal.organization_id != group.organization_id
                ):
                    raise RuntimeError("Group deletion facts changed the actor or scope.")
                ActionAuthorizationService.require_authorization_from_facts(
                    access=access, facts=facts.action
                )
                if not facts.is_manager or facts.action.principal.kind is not PrincipalKind.HUMAN:
                    raise AccessDeniedError()
                scope = ProjectActionAuthorizationDTO(group.organization_id, group.project_id)
                operation = await self._operation_idempotency.reserve_or_recover(
                    context=context,
                    access=access,
                    authorization=scope,
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                    lookup_authority=authority,
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    completed = self._require_safe_completed_operation(operation)
                    original = await self._group_deletion_result_reader.original(
                        organization_id=group.organization_id,
                        actor_id=access.actor_principal_id,
                        command=command,
                        operation_id=completed.operation_id,
                    )
                    # Current management precedes recovery of this request's immutable receipt.
                    if original != DeletedAccessGroupDTO(
                        operation_id=completed.operation_id,
                        organization_id=group.organization_id,
                        project_id=group.project_id,
                        group_id=group.group_id,
                        actor_principal_id=access.actor_principal_id,
                        access_revision=command.expected_access_revision + 1,
                    ):
                        raise ConflictError("The original group deletion result is incoherent.")
                    return AccessGroupDeletionResultDTO(original, completed)
                if command.expected_access_revision != group.access_revision:
                    raise StaleRevisionError()
                if group.access_revision == RevisionValidation.MAX_VALUE:
                    raise ConflictError("The Project Access revision cannot advance.")
                deleted = DeletedAccessGroupDTO(
                    operation_id=operation.operation_id,
                    organization_id=group.organization_id,
                    project_id=group.project_id,
                    group_id=group.group_id,
                    actor_principal_id=access.actor_principal_id,
                    access_revision=group.access_revision + 1,
                )
                binding = await self._deletion_status_binding_writer.bind_original_request(
                    reservation=operation,
                    request_id=request_id,
                    expected_installation_id=facts.installation_id,
                    expected_request=OperationReservationRequestDTO(
                        principal_id=access.actor_principal_id,
                        organization_id=group.organization_id,
                        project_id=group.project_id,
                        method=context.method,
                        requested_route=context.requested_route,
                        key=context.key,
                        fingerprint=fingerprint.value,
                        lookup_authority=authority,
                    ),
                )
                await self._group_deletion_writer.delete(
                    group=deleted, expected_project_revision=group.access_revision, binding=binding
                )
                completed = self._require_safe_completed_operation(
                    await self._operation_idempotency.record_completed_result(
                        operation, replay_kind=OperationReplayKind.SAFE_RESULT
                    )
                )
                if completed.operation_id != operation.operation_id:
                    raise RuntimeError("Group deletion completion changed the original operation.")
                return AccessGroupDeletionResultDTO(deleted, completed)
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @staticmethod
    def _require_safe_completed_operation(operation: object) -> CompletedSynchronousOperationDTO:
        """Require a replay-safe synchronous completion before using a deletion outcome."""
        if (
            not isinstance(operation, CompletedSynchronousOperationDTO)
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
        ):
            raise ConflictError("Group deletion has no safe original result.")
        return operation
