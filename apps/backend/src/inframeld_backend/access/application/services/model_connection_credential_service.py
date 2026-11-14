import asyncio
from datetime import UTC, datetime
from json import dumps
from typing import override
from uuid import uuid4

from inframeld_backend.access.application.commands.change_model_connection_credential_command import (
    ChangeModelConnectionCredentialCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_credential_dto import (
    ModelConnectionCredentialDTO,
)
from inframeld_backend.access.application.dtos.model_connection_credential_facts_dto import (
    ModelConnectionCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.model_connection_credential_result_dto import (
    ModelConnectionCredentialResultDTO,
)
from inframeld_backend.access.application.dtos.provider_credential_binding_dto import (
    ProviderCredentialBindingDTO,
)
from inframeld_backend.access.application.protocols.model_connection_credential_manager import (
    ModelConnectionCredentialManager,
)
from inframeld_backend.access.application.protocols.model_connection_credential_repository import (
    ModelConnectionCredentialRepository,
)
from inframeld_backend.access.application.protocols.provider_credential_cipher import (
    ProviderCredentialCipher,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.model_connection_destination_policy import (
    ModelConnectionDestinationPolicy,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ModelConnectionCredentialService(ModelConnectionCredentialManager):
    def __init__(
        self,
        transactions: TransactionManager,
        repository: ModelConnectionCredentialRepository,
        idempotency: OperationIdempotency,
        fingerprints: RequestFingerprintService,
        cipher: ProviderCredentialCipher,
        destination_policy: ModelConnectionDestinationPolicy,
    ) -> None:
        self._transactions = transactions
        self._repository = repository
        self._idempotency = idempotency
        self._fingerprints = fingerprints
        self._cipher = cipher
        self._destination_policy = destination_policy

    @override
    async def get(
        self, access: AccessContextDTO, project_id: ProjectId, connection_id: ModelConnectionId
    ) -> ModelConnectionCredentialDTO:
        try:
            async with asyncio.timeout(5), self._transactions.begin():
                facts = await self._require_authority(
                    access, project_id, connection_id, for_write=False
                )
                return facts.credential
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @override
    async def change(
        self,
        access: AccessContextDTO,
        command: ChangeModelConnectionCredentialCommand,
        context: IdempotencyContextDTO,
    ) -> ModelConnectionCredentialResultDTO:
        try:
            RevisionValidation.require(command.expected_revision)
        except (TypeError, ValueError):
            raise InvalidInputError() from None
        method = HttpMethod.DELETE if command.value is None else HttpMethod.PUT
        route = (
            f"/v1/projects/{command.project_id.value}"
            f"/model-connections/{command.connection_id.value}/credential"
        )
        if context.method is not method or context.requested_route != route:
            raise RuntimeError("Credential management changed the exact operation route.")
        fingerprint = self._fingerprints.fingerprint(
            purpose="access.model-connection.credential:v1",
            canonical_request=dumps(
                [
                    route,
                    method.value,
                    command.expected_revision,
                    command.value.value if command.value is not None else None,
                ],
                separators=(",", ":"),
            ).encode("ascii"),
        )
        try:
            async with asyncio.timeout(5), self._transactions.begin():
                facts = await self._require_authority(
                    access, command.project_id, command.connection_id, for_write=True
                )
                operation = await self._idempotency.reserve_or_recover(
                    context=context,
                    access=access,
                    authorization=facts,
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    if not isinstance(operation, CompletedSynchronousOperationDTO):
                        raise ConflictError("The original credential result is unavailable.")
                    return await self._recover(facts, command, operation)

                credential = facts.credential
                if credential.revision != command.expected_revision:
                    raise StaleRevisionError()
                changed = command.value is not None or credential.present
                if changed and credential.revision == RevisionValidation.MAX_VALUE:
                    raise ConflictError("The credential revision is exhausted.")
                if command.value is not None:
                    connection = facts.connection_access
                    if (
                        connection.authentication is not ModelConnectionAuthentication.API_KEY
                        or not self._destination_policy.permits(
                            provider=connection.provider,
                            base_url=connection.base_url,
                            api_version=connection.api_version,
                            authentication=connection.authentication,
                        )
                    ):
                        raise InvalidInputError(
                            "The connection does not accept a provider credential."
                        )
                    credential_id = credential.credential_id or uuid4()
                    target = ProviderCredentialBindingDTO(
                        facts.organization_id,
                        facts.project_id,
                        command.connection_id,
                        credential_id,
                        credential.revision + 1,
                    )
                    envelope = self._cipher.encrypt(command.value, target, facts.key_id)
                else:
                    self._cipher.require_key(facts.key_id)
                    credential_id = credential.credential_id
                    envelope = None
                if changed:
                    credential = ModelConnectionCredentialDTO(
                        facts.project_id,
                        command.connection_id,
                        credential_id,
                        credential.revision + 1,
                        envelope is not None,
                        datetime.now(UTC),
                    )
                    await self._repository.save(facts, credential, envelope, operation.operation_id)
                completed = await self._idempotency.record_completed_result(
                    operation, replay_kind=OperationReplayKind.SAFE_RESULT
                )
                if (
                    not isinstance(completed, CompletedSynchronousOperationDTO)
                    or completed.operation_id != operation.operation_id
                    or completed.replay_kind is not OperationReplayKind.SAFE_RESULT
                    or not completed.created
                ):
                    raise ConflictError("The new credential result is unavailable.")
                result = ModelConnectionCredentialResultDTO(credential, changed, completed)
                await self._repository.save_result(facts, result)
                return result
        except TimeoutError:
            raise DependencyUnavailableError() from None

    async def _require_authority(
        self,
        access: AccessContextDTO,
        project_id: ProjectId,
        connection_id: ModelConnectionId,
        *,
        for_write: bool,
    ) -> ModelConnectionCredentialFactsDTO:
        facts = await self._repository.inspect(
            access, project_id, connection_id, for_write=for_write
        )
        if facts is None:
            raise ResourceNotFoundError()
        principal = facts.action.principal
        if (
            facts.project_id != project_id
            or facts.credential.project_id != project_id
            or facts.credential.connection_id != connection_id
            or principal.id != access.actor_principal_id
            or principal.organization_id != facts.organization_id
        ):
            raise RuntimeError("Credential management changed the actor or exact target.")
        PrincipalAccessEvaluationService.require_human(access=access, principal=principal)
        if principal.kind is not PrincipalKind.HUMAN:
            raise AccessDeniedError()
        ActionAuthorizationService.require_authorization_from_facts(
            access=access, facts=facts.action
        )
        return facts

    async def _recover(
        self,
        facts: ModelConnectionCredentialFactsDTO,
        command: ChangeModelConnectionCredentialCommand,
        completed: CompletedSynchronousOperationDTO,
    ) -> ModelConnectionCredentialResultDTO:
        if completed.replay_kind is not OperationReplayKind.SAFE_RESULT or completed.created:
            raise ConflictError("The original credential result is unavailable.")
        original = await self._repository.original(facts, completed)
        credential = original.credential
        if (
            original.operation != completed
            or credential.project_id != command.project_id
            or credential.connection_id != command.connection_id
            or credential.present != (command.value is not None)
            or (command.value is not None and not original.changed)
            or credential.revision != command.expected_revision + int(original.changed)
            or (credential.credential_id is None) != (credential.revision == 0)
            or (credential.changed_at is None) != (credential.revision == 0)
        ):
            raise ConflictError("The original credential result is incoherent.")
        return original
