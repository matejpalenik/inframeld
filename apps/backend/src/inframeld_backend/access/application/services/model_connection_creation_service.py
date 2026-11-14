import asyncio
from json import dumps
from typing import override
from uuid import uuid4

from inframeld_backend.access.application.commands.create_model_connection_command import (
    CreateModelConnectionCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_creation_dto import (
    ModelConnectionCreationDTO,
)
from inframeld_backend.access.application.dtos.model_connection_dto import ModelConnectionDTO
from inframeld_backend.access.application.protocols.model_connection_creation_repository import (
    ModelConnectionCreationRepository,
)
from inframeld_backend.access.application.protocols.model_connection_creator import (
    ModelConnectionCreator,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.policies.model_connection_destination_policy import (
    ModelConnectionDestinationPolicy,
)
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
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation

_INITIAL_ACTIONS = tuple(ModelConnectionAction)


class ModelConnectionCreationService(ModelConnectionCreator):
    def __init__(
        self,
        transaction_manager: TransactionManager,
        creation_repository: ModelConnectionCreationRepository,
        operation_idempotency: OperationIdempotency,
        request_fingerprints: RequestFingerprintService,
        destination_policy: ModelConnectionDestinationPolicy,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._creation_repository = creation_repository
        self._operation_idempotency = operation_idempotency
        self._request_fingerprints = request_fingerprints
        self._destination_policy = destination_policy

    @override
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateModelConnectionCommand,
        context: IdempotencyContextDTO,
    ) -> ModelConnectionCreationDTO:
        route = f"/v1/projects/{command.project_id.value}/model-connections"
        if context.method != "POST" or context.requested_route != route:
            raise RuntimeError("Model connection creation changed its original route.")
        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = await self._creation_repository.lock_for_creation(
                    access, command.project_id
                )
                if facts is None:
                    raise ResourceNotFoundError()
                if (
                    facts.project_id != command.project_id
                    or facts.action.principal.id != access.actor_principal_id
                    or facts.action.principal.organization_id != facts.organization_id
                ):
                    raise RuntimeError("Model connection creation changed the actor or Project.")
                PrincipalAccessEvaluationService.require_human(
                    access=access, principal=facts.action.principal
                )
                if facts.action.principal.kind is not PrincipalKind.HUMAN:
                    raise AccessDeniedError()
                ActionAuthorizationService.require_authorization_from_facts(
                    access=access, facts=facts.action
                )

                operation = await self._operation_idempotency.reserve_or_recover(
                    context=context,
                    access=access,
                    authorization=facts,
                    fingerprint=self._fingerprint(command),
                    expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                    lookup_authority=OperationLookupAuthority(
                        OperationLookupAuthorityFamily.PROJECT_ACTION_USE,
                        ActionId(ProjectAction.CREATE_MODEL_CONNECTIONS.value),
                    ),
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    completed = self._safe_completion(operation)
                    original = await self._creation_repository.original(access, facts, completed)
                    if (
                        original.operation != completed
                        or original.connection.project_id != command.project_id
                        or original.connection.name != command.name
                        or original.connection.display_name != command.display_name.value
                        or original.connection.access != command.access
                        or original.initial_actions != _INITIAL_ACTIONS
                    ):
                        raise ConflictError(
                            "The original model connection creation result is incoherent."
                        )
                    return original

                if not self._destination_policy.permits(
                    provider=command.access.provider,
                    base_url=command.access.base_url,
                    api_version=command.access.api_version,
                    authentication=command.access.authentication,
                ):
                    raise InvalidInputError(
                        "The model destination is not approved for this access profile."
                    )
                RevisionValidation.require(facts.access_revision)
                if facts.access_revision == RevisionValidation.MAX_VALUE:
                    raise ConflictError("The Project access revision is exhausted.")
                connection = ModelConnectionDTO(
                    command.project_id,
                    ModelConnectionId(uuid4()),
                    command.name,
                    command.display_name.value,
                    command.access,
                    connection_access_revision=0,
                    credential_present=False,
                    credential_revision=0,
                )
                await self._creation_repository.save(
                    access, facts, operation.operation_id, connection, _INITIAL_ACTIONS
                )
                completed = self._safe_completion(
                    await self._operation_idempotency.record_completed_result(
                        operation, replay_kind=OperationReplayKind.SAFE_RESULT
                    )
                )
                if completed.operation_id != operation.operation_id:
                    raise RuntimeError("Model connection creation changed its original operation.")
                return ModelConnectionCreationDTO(
                    connection, completed, facts.access_revision + 1, _INITIAL_ACTIONS
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None

    def _fingerprint(self, command: CreateModelConnectionCommand) -> RequestFingerprint:
        canonical_request = dumps(
            {
                "projectId": str(command.project_id.value),
                "name": command.name.value,
                "displayName": command.display_name.value,
                "provider": command.access.provider.value,
                "baseUrl": command.access.base_url,
                "apiVersion": command.access.api_version,
                "authentication": command.access.authentication.value,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return self._request_fingerprints.fingerprint(
            purpose="access.model-connection.create:v1", canonical_request=canonical_request
        )

    @staticmethod
    def _safe_completion(operation: object) -> CompletedSynchronousOperationDTO:
        if (
            not isinstance(operation, CompletedSynchronousOperationDTO)
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
        ):
            raise ConflictError("Model connection creation has no safe completed result.")
        return operation
