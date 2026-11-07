import asyncio
from typing import override
from uuid import uuid4

from inframeld_backend.access.application.commands.create_access_group_command import (
    CreateAccessGroupCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_creation_result_dto import (
    AccessGroupCreationResultDTO,
)
from inframeld_backend.access.application.dtos.created_access_group_dto import (
    CreatedAccessGroupDTO,
)
from inframeld_backend.access.application.protocols.access_group_creation_facts_reader import (
    AccessGroupCreationFactsReader,
)
from inframeld_backend.access.application.protocols.access_group_creation_result_reader import (
    AccessGroupCreationResultReader,
)
from inframeld_backend.access.application.protocols.access_group_creation_writer import (
    AccessGroupCreationWriter,
)
from inframeld_backend.access.application.protocols.access_group_creator import (
    AccessGroupCreator,
)
from inframeld_backend.access.application.services.access_group_creation_fingerprint_service import (
    AccessGroupCreationFingerprintService,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
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
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class AccessGroupCreationService(AccessGroupCreator):
    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        creation_facts_reader: AccessGroupCreationFactsReader,
        creation_writer: AccessGroupCreationWriter,
        creation_result_reader: AccessGroupCreationResultReader,
        operation_idempotency: OperationIdempotency,
        creation_fingerprint_service: AccessGroupCreationFingerprintService,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._creation_facts_reader = creation_facts_reader
        self._creation_writer = creation_writer
        self._creation_result_reader = creation_result_reader
        self._operation_idempotency = operation_idempotency
        self._creation_fingerprint_service = creation_fingerprint_service

    @override
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateAccessGroupCommand,
        context: IdempotencyContextDTO,
    ) -> AccessGroupCreationResultDTO:
        route = f"/v1/projects/{command.project_id.value}/access-groups"
        if context.method != "POST" or context.requested_route != route:
            raise RuntimeError("Group creation changed its original route.")
        fingerprint = self._creation_fingerprint_service.for_create(command)

        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = await self._creation_facts_reader.lock_for_creation(
                    access=access, project_id=command.project_id
                )
                if facts is None:
                    raise ResourceNotFoundError()
                if (
                    facts.project_id != command.project_id
                    or facts.action.principal.id != access.actor_principal_id
                    or facts.organization_id != facts.action.principal.organization_id
                ):
                    raise RuntimeError("Group creation facts changed the actor or scope.")
                RevisionValidation.require(facts.access_revision)
                PrincipalAccessEvaluationService.require_human(
                    access=access, principal=facts.action.principal
                )
                ActionAuthorizationService.require_authorization_from_facts(
                    access=access, facts=facts.action
                )
                if facts.action.principal.kind is not PrincipalKind.HUMAN:
                    raise AccessDeniedError()

                operation = await self._operation_idempotency.reserve_or_recover(
                    context=context,
                    access=access,
                    authorization=facts,
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                    lookup_authority=OperationLookupAuthority(
                        OperationLookupAuthorityFamily.PROJECT_ACTION_USE,
                        ActionId(ProjectAction.CREATE_ACCESS_GROUPS.value),
                    ),
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    completed = self._require_safe_completed_operation(operation)
                    original = await self._creation_result_reader.original(
                        organization_id=facts.organization_id,
                        project_id=facts.project_id,
                        actor_id=access.actor_principal_id,
                        operation_id=completed.operation_id,
                    )
                    if (
                        original.operation_id != completed.operation_id
                        or original.organization_id != facts.organization_id
                        or original.project_id != command.project_id
                        or original.creator_principal_id != access.actor_principal_id
                        or original.name != command.name
                        or original.display_name != command.display_name.value
                        or original.access_revision != command.expected_access_revision + 1
                    ):
                        raise ConflictError("The original group creation result is incoherent.")
                    return AccessGroupCreationResultDTO(original, completed)

                if command.expected_access_revision != facts.access_revision:
                    raise StaleRevisionError()
                if facts.access_revision == RevisionValidation.MAX_VALUE:
                    raise ConflictError("The Project access revision is exhausted.")
                group = CreatedAccessGroupDTO(
                    operation_id=operation.operation_id,
                    organization_id=facts.organization_id,
                    project_id=facts.project_id,
                    group_id=AccessGroupId(uuid4()),
                    creator_principal_id=access.actor_principal_id,
                    name=command.name,
                    display_name=command.display_name.value,
                    access_revision=facts.access_revision + 1,
                )
                await self._creation_writer.create(
                    group=group, expected_project_revision=facts.access_revision
                )
                completed = self._require_safe_completed_operation(
                    await self._operation_idempotency.record_completed_result(
                        operation, replay_kind=OperationReplayKind.SAFE_RESULT
                    )
                )
                if completed.operation_id != operation.operation_id:
                    raise RuntimeError("Group creation completion changed its original operation.")
                return AccessGroupCreationResultDTO(group, completed)
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @staticmethod
    def _require_safe_completed_operation(operation: object) -> CompletedSynchronousOperationDTO:
        """Accept only retained synchronous outcomes supported by group creation."""
        if (
            not isinstance(operation, CompletedSynchronousOperationDTO)
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
        ):
            raise ConflictError("Group creation has no safe completed result.")
        return operation
