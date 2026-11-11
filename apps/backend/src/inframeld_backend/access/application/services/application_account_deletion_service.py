import asyncio
from typing import override

from inframeld_backend.access.application.commands.delete_application_account_command import (
    DeleteApplicationAccountCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_deletion_facts_dto import (
    ApplicationAccountDeletionFactsDTO,
)
from inframeld_backend.access.application.dtos.application_account_deletion_record_dto import (
    ApplicationAccountDeletionRecordDTO,
)
from inframeld_backend.access.application.dtos.application_account_deletion_result_dto import (
    ApplicationAccountDeletionResultDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.protocols.application_account_deleter import (
    ApplicationAccountDeleter,
)
from inframeld_backend.access.application.protocols.application_account_deletion_facts_reader import (
    ApplicationAccountDeletionFactsReader,
)
from inframeld_backend.access.application.protocols.application_account_deletion_writer import (
    ApplicationAccountDeletionWriter,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.application_account_deletion_fingerprint_service import (
    ApplicationAccountDeletionFingerprintService,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
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


class ApplicationAccountDeletionService(ApplicationAccountDeleter):
    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        deletion_facts_reader: ApplicationAccountDeletionFactsReader,
        deletion_writer: ApplicationAccountDeletionWriter,
        operation_idempotency: OperationIdempotency,
        deletion_fingerprint_service: ApplicationAccountDeletionFingerprintService,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._deletion_facts_reader = deletion_facts_reader
        self._deletion_writer = deletion_writer
        self._operation_idempotency = operation_idempotency
        self._deletion_fingerprint_service = deletion_fingerprint_service

    @override
    async def delete(
        self,
        *,
        access: AccessContextDTO,
        command: DeleteApplicationAccountCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationAccountDeletionResultDTO:
        route = (
            f"/v1/projects/{command.project_id.value}/application-accounts/"
            f"{command.application_principal_id.value}"
        )
        if context.method != HttpMethod.DELETE or context.requested_route != route:
            raise RuntimeError("Application-account deletion changed its original method or route.")

        fingerprint = self._deletion_fingerprint_service.for_delete(command)
        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = await self._deletion_facts_reader.lock_for_deletion(
                    access=access, command=command
                )
                if facts is None:
                    raise ResourceNotFoundError()
                self._authorize(access, command, facts)
                operation = await self._operation_idempotency.reserve_or_recover(
                    context=context,
                    access=access,
                    authorization=ProjectActionAuthorizationDTO(
                        facts.organization_id, facts.project_id
                    ),
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    completed = self._completion(operation, created=False)
                    original = await self._deletion_facts_reader.read_original(
                        organization_id=facts.organization_id,
                        project_id=facts.project_id,
                        actor_principal_id=access.actor_principal_id,
                        operation_id=completed.operation_id,
                    )
                    if original is None:
                        raise DependencyUnavailableError()
                    if (
                        original.operation_id != completed.operation_id
                        or original.installation_id != facts.installation_id
                        or original.organization_id != facts.organization_id
                        or original.project_id != command.project_id
                        or original.actor_principal_id != access.actor_principal_id
                        or original.application_principal_id != command.application_principal_id
                        or original.access_revision != command.expected_access_revision + 1
                    ):
                        raise ConflictError(
                            "The original application-account result is incoherent."
                        )
                    return ApplicationAccountDeletionResultDTO(original, completed)

                if command.expected_access_revision != facts.access_revision:
                    raise StaleRevisionError()
                if facts.access_revision == RevisionValidation.MAX_VALUE:
                    raise ConflictError("The Project access revision is exhausted.")
                if facts.application_principal.status is PrincipalStatus.RETIRED:
                    raise ConflictError("The application account is already retired.")

                original = ApplicationAccountDeletionRecordDTO(
                    operation_id=operation.operation_id,
                    installation_id=facts.installation_id,
                    organization_id=facts.organization_id,
                    project_id=facts.project_id,
                    actor_principal_id=access.actor_principal_id,
                    application_principal_id=command.application_principal_id,
                    access_revision=facts.access_revision + 1,
                )
                await self._deletion_writer.save(
                    original=original,
                    expected_project_revision=facts.access_revision,
                    checked_at=facts.checked_at,
                )
                completed = self._completion(
                    await self._operation_idempotency.record_completed_result(
                        operation, replay_kind=OperationReplayKind.SAFE_RESULT
                    ),
                    created=True,
                )
                if completed.operation_id != operation.operation_id:
                    raise RuntimeError(
                        "Application-account completion changed its original operation."
                    )
                return ApplicationAccountDeletionResultDTO(original, completed)
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @staticmethod
    def _authorize(
        access: AccessContextDTO,
        command: DeleteApplicationAccountCommand,
        facts: ApplicationAccountDeletionFactsDTO,
    ) -> None:
        if (
            facts.project_id != command.project_id
            or facts.actor.principal.id != access.actor_principal_id
            or facts.organization_id != facts.actor.principal.organization_id
            or facts.application_principal.id != command.application_principal_id
            or facts.application_principal.organization_id != facts.organization_id
            or facts.application_principal.kind is not PrincipalKind.APPLICATION
        ):
            raise RuntimeError("Application-account facts changed the actor or target scope.")
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
            raise ConflictError("Application-account deletion has no coherent completed result.")
        return value
