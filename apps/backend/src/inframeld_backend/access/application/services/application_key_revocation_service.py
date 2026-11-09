import asyncio
from dataclasses import replace
from typing import override

from inframeld_backend.access.application.commands.revoke_application_key_command import (
    RevokeApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_revocation_facts_dto import (
    ApplicationKeyRevocationFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_revocation_record_dto import (
    ApplicationKeyRevocationRecordDTO,
)
from inframeld_backend.access.application.dtos.application_key_revocation_result_dto import (
    ApplicationKeyRevocationResultDTO,
)
from inframeld_backend.access.application.protocols.application_key_revocation_facts_reader import (
    ApplicationKeyRevocationFactsReader,
)
from inframeld_backend.access.application.protocols.application_key_revocation_writer import (
    ApplicationKeyRevocationWriter,
)
from inframeld_backend.access.application.protocols.application_key_revoker import (
    ApplicationKeyRevoker,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.application_key_revocation_fingerprint_service import (
    ApplicationKeyRevocationFingerprintService,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
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
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ApplicationKeyRevocationService(ApplicationKeyRevoker):
    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        revocation_facts_reader: ApplicationKeyRevocationFactsReader,
        revocation_writer: ApplicationKeyRevocationWriter,
        operation_idempotency: OperationIdempotency,
        revocation_fingerprint_service: ApplicationKeyRevocationFingerprintService,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._revocation_facts_reader = revocation_facts_reader
        self._revocation_writer = revocation_writer
        self._operation_idempotency = operation_idempotency
        self._revocation_fingerprint_service = revocation_fingerprint_service

    @override
    async def revoke(
        self,
        *,
        access: AccessContextDTO,
        command: RevokeApplicationKeyCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationKeyRevocationResultDTO:
        route = (
            f"/v1/projects/{command.project_id.value}/application-accounts/"
            f"{command.application_principal_id.value}/keys/{command.key_id.value}/revoke"
        )
        if context.method != HttpMethod.POST or context.requested_route != route:
            raise RuntimeError("Application-key revocation changed its original method or route.")

        fingerprint = self._revocation_fingerprint_service.for_revoke(command)
        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = await self._revocation_facts_reader.lock_for_revoke(
                    access=access, command=command
                )
                if facts is None:
                    raise ResourceNotFoundError()
                self._authorize(access, command, facts)
                metadata = facts.metadata
                if metadata is None:
                    raise ResourceNotFoundError()

                operation = await self._operation_idempotency.reserve_or_recover(
                    context=context,
                    access=access,
                    authorization=facts,
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    completed = self._completion(operation, created=False)
                    original = await self._revocation_facts_reader.read_original(
                        organization_id=facts.organization_id,
                        project_id=facts.project_id,
                        actor_principal_id=access.actor_principal_id,
                        operation_id=completed.operation_id,
                    )
                    if original is None:
                        raise DependencyUnavailableError()
                    if (
                        original.operation_id != completed.operation_id
                        or original.organization_id != facts.organization_id
                        or original.installation_id != facts.installation_id
                        or original.actor_principal_id != access.actor_principal_id
                        or original.metadata.project_id != command.project_id
                        or original.metadata.application_principal_id
                        != command.application_principal_id
                        or original.metadata.key_id != command.key_id
                        or original.metadata.revoked_at is None
                        or original.access_revision
                        not in (
                            command.expected_access_revision,
                            command.expected_access_revision + 1,
                        )
                    ):
                        raise ConflictError("The original application-key result is incoherent.")
                    return ApplicationKeyRevocationResultDTO(original, completed)

                if command.expected_access_revision != facts.access_revision:
                    raise StaleRevisionError()

                revision = facts.access_revision
                if metadata.revoked_at is None:
                    if revision == RevisionValidation.MAX_VALUE:
                        raise ConflictError("The Project access revision is exhausted.")
                    revision += 1
                    metadata = replace(metadata, revoked_at=facts.checked_at)

                original = ApplicationKeyRevocationRecordDTO(
                    operation_id=operation.operation_id,
                    organization_id=facts.organization_id,
                    installation_id=facts.installation_id,
                    actor_principal_id=access.actor_principal_id,
                    access_revision=revision,
                    metadata=metadata,
                )
                await self._revocation_writer.save(
                    original=original, expected_project_revision=facts.access_revision
                )
                completed = self._completion(
                    await self._operation_idempotency.record_completed_result(
                        operation, replay_kind=OperationReplayKind.SAFE_RESULT
                    ),
                    created=True,
                )
                if completed.operation_id != operation.operation_id:
                    raise RuntimeError("Application-key completion changed its original operation.")
                return ApplicationKeyRevocationResultDTO(original, completed)
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @staticmethod
    def _authorize(
        access: AccessContextDTO,
        command: RevokeApplicationKeyCommand,
        facts: ApplicationKeyRevocationFactsDTO,
    ) -> None:
        if (
            facts.project_id != command.project_id
            or facts.actor.principal.id != access.actor_principal_id
            or facts.organization_id != facts.actor.principal.organization_id
            or facts.application_principal.id != command.application_principal_id
            or facts.application_principal.organization_id != facts.organization_id
            or facts.application_principal.kind is not PrincipalKind.APPLICATION
            or (
                facts.metadata is not None
                and (
                    facts.metadata.project_id != command.project_id
                    or facts.metadata.application_principal_id != command.application_principal_id
                    or facts.metadata.key_id != command.key_id
                )
            )
        ):
            raise RuntimeError("Application-key facts changed the actor or target scope.")

        RevisionValidation.require(facts.access_revision)
        PrincipalAccessEvaluationService.require_human(
            access=access, principal=facts.actor.principal
        )
        ActionAuthorizationService.require_authorization_from_facts(
            access=access, facts=facts.actor
        )

    @staticmethod
    def _completion(value: object, *, created: bool) -> CompletedSynchronousOperationDTO:
        if (
            not isinstance(value, CompletedSynchronousOperationDTO)
            or value.replay_kind is not OperationReplayKind.SAFE_RESULT
            or value.created is not created
        ):
            raise ConflictError("Application-key revocation has no coherent completed result.")
        return value
