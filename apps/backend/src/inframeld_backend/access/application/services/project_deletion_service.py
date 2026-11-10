import asyncio
from typing import override
from uuid import uuid4

from inframeld_backend.access.application.commands.delete_project_command import (
    DeleteProjectCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_deletion_facts_dto import (
    ProjectDeletionFactsDTO,
)
from inframeld_backend.access.application.dtos.project_deletion_result_dto import (
    ProjectDeletionResultDTO,
)
from inframeld_backend.access.application.protocols.project_deleter import ProjectDeleter
from inframeld_backend.access.application.protocols.project_deletion_admission_writer import (
    ProjectDeletionAdmissionWriter,
)
from inframeld_backend.access.application.protocols.project_deletion_facts_reader import (
    ProjectDeletionFactsReader,
)
from inframeld_backend.access.application.protocols.project_deletion_result_reader import (
    ProjectDeletionResultReader,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.application.services.project_deletion_fingerprint_service import (
    ProjectDeletionFingerprintService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.policies.action_authorization_policy import (
    ActionAuthorizationPolicy,
)
from inframeld_backend.access.domain.policy_inputs.action_authorization_policy_input import (
    ActionAuthorizationPolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.project_deletion_obligation_id import (
    ProjectDeletionObligationId,
)
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
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
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ProjectDeletionService(ProjectDeleter):
    """Coordinate guarded deletion admission, independently of its future SQL/worker adapters."""

    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        project_deletion_facts_reader: ProjectDeletionFactsReader,
        project_deletion_admission_writer: ProjectDeletionAdmissionWriter,
        project_deletion_result_reader: ProjectDeletionResultReader,
        operation_idempotency: OperationIdempotency,
        project_deletion_fingerprint_service: ProjectDeletionFingerprintService,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._project_deletion_facts_reader = project_deletion_facts_reader
        self._project_deletion_admission_writer = project_deletion_admission_writer
        self._project_deletion_result_reader = project_deletion_result_reader
        self._operation_idempotency = operation_idempotency
        self._project_deletion_fingerprint_service = project_deletion_fingerprint_service

    @override
    async def delete(
        self,
        *,
        access: AccessContextDTO,
        command: DeleteProjectCommand,
        context: IdempotencyContextDTO,
        request_id: RequestId,
    ) -> ProjectDeletionResultDTO:
        route = f"/v1/projects/{command.project_id.value}"
        if context.method is not HttpMethod.DELETE or context.requested_route != route:
            raise RuntimeError("Project deletion changed its original method or route.")

        fingerprint = self._project_deletion_fingerprint_service.for_delete(command)
        authority = OperationLookupAuthority(
            OperationLookupAuthorityFamily.PROJECT_ACTION_USE,
            ActionId(ProjectAction.DELETE_PROJECT.value),
        )
        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = await self._project_deletion_facts_reader.lock_for_deletion(
                    access=access, project_id=command.project_id
                )
                if facts is None:
                    raise ResourceNotFoundError()

                self._require_current_authority(access=access, command=command, facts=facts)
                scope = ProjectActionAuthorizationDTO(facts.organization_id, facts.project_id)
                operation = await self._operation_idempotency.reserve_or_recover(
                    context=context,
                    access=access,
                    authorization=scope,
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.ASYNC_JOB,
                    lookup_authority=authority,
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    accepted = self._require_accepted_operation(operation, created=False)
                    original = await self._project_deletion_result_reader.original(
                        installation_id=facts.installation_id,
                        organization_id=scope.organization_id,
                        project_id=scope.project_id,
                        actor_principal_id=access.actor_principal_id,
                        operation=accepted,
                    )
                    self._require_matching_original(
                        original=original,
                        accepted=accepted,
                        facts=facts,
                        command=command,
                        access=access,
                    )
                    return original

                if facts.action.project_status is not ProjectStatus.ACTIVE:
                    raise ConflictError("The Project already has a deletion obligation.")
                if facts.access_revision != command.expected_access_revision:
                    raise StaleRevisionError()
                if facts.access_revision == RevisionValidation.MAX_VALUE:
                    raise ConflictError("The Project Access revision cannot advance.")

                obligation_id = ProjectDeletionObligationId(uuid4())
                job_id = JobId(uuid4())
                await self._project_deletion_admission_writer.admit(
                    installation_id=facts.installation_id,
                    scope=scope,
                    access=access,
                    command=command,
                    context=context,
                    request_id=request_id,
                    reservation=operation,
                    fingerprint=fingerprint,
                    obligation_id=obligation_id,
                    job_id=job_id,
                )
                accepted = self._require_accepted_operation(
                    await self._operation_idempotency.record_completed_result(
                        operation, replay_kind=OperationReplayKind.ASYNC_JOB
                    ),
                    created=True,
                )
                if (
                    accepted.operation_id != operation.operation_id
                    or accepted.expires_at is not None
                ):
                    raise ConflictError("Unfinished deletion changed its original admission.")

                return ProjectDeletionResultDTO(
                    installation_id=facts.installation_id,
                    organization_id=scope.organization_id,
                    project_id=scope.project_id,
                    actor_principal_id=access.actor_principal_id,
                    obligation_id=obligation_id,
                    job_id=job_id,
                    before_access_revision=facts.access_revision,
                    access_revision=facts.access_revision + 1,
                    operation=accepted,
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @staticmethod
    def _require_current_authority(
        *, access: AccessContextDTO, command: DeleteProjectCommand, facts: ProjectDeletionFactsDTO
    ) -> None:
        """Check live Delete authority before history, including an already blocked Project.

        DELETING permits only original-result recovery here. It never supplies
        continuation authority or makes a fresh admission eligible.
        """
        action = facts.action
        if (
            facts.project_id != command.project_id
            or action.principal.id != access.actor_principal_id
            or action.principal.organization_id != facts.organization_id
        ):
            raise RuntimeError("Project deletion facts changed the actor or scope.")

        PrincipalAccessEvaluationService.require_human(access=access, principal=action.principal)
        principal_access = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=action.principal,
            has_pending_recovery=action.has_pending_recovery,
            oauth_credential_facts=action.oauth_credential_facts,
            application_key_facts=action.application_key_facts,
        )
        PrincipalAccessEvaluationService.require_current_credential(
            access=access, principal_access=principal_access
        )
        if not action.is_project_member:
            raise ResourceNotFoundError()

        if action.principal.kind is not PrincipalKind.HUMAN or not (
            ActionAuthorizationPolicy.may_perform_action(
                ActionAuthorizationPolicyInput(
                    principal_access=principal_access,
                    is_project_member=action.is_project_member,
                    has_exact_action_grant=action.has_exact_action_grant,
                )
            )
        ):
            raise AccessDeniedError()

    @staticmethod
    def _require_accepted_operation(
        operation: object, *, created: bool
    ) -> AcceptedAsyncOperationDTO:
        """Reject uncertainty or incompatible metadata without admitting replacement work."""
        if not isinstance(operation, AcceptedAsyncOperationDTO) or operation.created is not created:
            raise ConflictError("Project deletion has no matching original acceptance.")
        return operation

    @staticmethod
    def _require_matching_original(
        *,
        original: ProjectDeletionResultDTO,
        accepted: AcceptedAsyncOperationDTO,
        facts: ProjectDeletionFactsDTO,
        command: DeleteProjectCommand,
        access: AccessContextDTO,
    ) -> None:
        if (
            original.operation != accepted
            or original.installation_id != facts.installation_id
            or original.organization_id != facts.organization_id
            or original.project_id != facts.project_id
            or original.actor_principal_id != access.actor_principal_id
            or original.before_access_revision != command.expected_access_revision
            or original.access_revision != command.expected_access_revision + 1
        ):
            raise ConflictError("The original Project deletion result is incoherent.")
