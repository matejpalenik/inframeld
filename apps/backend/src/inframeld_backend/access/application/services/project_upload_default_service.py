import asyncio
from typing import override

from inframeld_backend.access.application.commands.set_project_upload_default_command import (
    SetProjectUploadDefaultCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_upload_default_change_result_dto import (
    ProjectUploadDefaultChangeResultDTO,
)
from inframeld_backend.access.application.dtos.project_upload_default_dto import (
    ProjectUploadDefaultDTO,
)
from inframeld_backend.access.application.dtos.project_upload_default_facts_dto import (
    ProjectUploadDefaultFactsDTO,
)
from inframeld_backend.access.application.dtos.project_upload_default_record_dto import (
    ProjectUploadDefaultRecordDTO,
)
from inframeld_backend.access.application.protocols.project_upload_default_changer import (
    ProjectUploadDefaultChanger,
)
from inframeld_backend.access.application.protocols.project_upload_default_facts_reader import (
    ProjectUploadDefaultFactsReader,
)
from inframeld_backend.access.application.protocols.project_upload_default_reader import (
    ProjectUploadDefaultReader,
)
from inframeld_backend.access.application.protocols.project_upload_default_repository import (
    ProjectUploadDefaultRepository,
)
from inframeld_backend.access.application.queries.get_project_upload_default_query import (
    GetProjectUploadDefaultQuery,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.application.services.project_upload_default_fingerprint_service import (
    ProjectUploadDefaultFingerprintService,
)
from inframeld_backend.access.domain.errors.project_upload_default_errors import (
    ProjectUploadDefaultStaleRevisionError,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
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
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.domain.errors.domain_errors import InvalidStateTransitionError
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ProjectUploadDefaultService(ProjectUploadDefaultReader, ProjectUploadDefaultChanger):
    """Coordinate current management, exact original recovery and future-only replacement."""

    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        default_facts_reader: ProjectUploadDefaultFactsReader,
        default_repository: ProjectUploadDefaultRepository,
        operation_idempotency: OperationIdempotency,
        default_fingerprint_service: ProjectUploadDefaultFingerprintService,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._default_facts_reader = default_facts_reader
        self._default_repository = default_repository
        self._operation_idempotency = operation_idempotency
        self._default_fingerprint_service = default_fingerprint_service

    @override
    async def get(
        self, *, access: AccessContextDTO, query: GetProjectUploadDefaultQuery
    ) -> ProjectUploadDefaultDTO:
        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = self._require_current_facts(
                    access=access,
                    project_id=query.project_id,
                    facts=await self._default_facts_reader.read(
                        access=access, project_id=query.project_id
                    ),
                    proposed=None,
                )
                return ProjectUploadDefaultDTO(
                    facts.organization_id, facts.project_id, facts.access_revision, facts.audience
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @override
    async def set(
        self,
        *,
        access: AccessContextDTO,
        command: SetProjectUploadDefaultCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectUploadDefaultChangeResultDTO:
        route = f"/v1/projects/{command.project_id.value}/upload-defaults"
        if context.method is not HttpMethod.PUT or context.requested_route != route:
            raise RuntimeError("Upload-default context changed its exact method or route.")
        fingerprint = self._default_fingerprint_service.for_set(command)
        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = self._require_current_facts(
                    access=access,
                    project_id=command.project_id,
                    facts=await self._default_facts_reader.lock_for_change(
                        access=access, command=command
                    ),
                    proposed=command.audience,
                )
                operation = await self._operation_idempotency.reserve_or_recover(
                    context=context,
                    access=access,
                    authorization=facts,
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    completed = self._require_safe_completed_operation(operation)
                    original = await self._default_repository.original(
                        organization_id=facts.organization_id,
                        project_id=facts.project_id,
                        actor_principal_id=access.actor_principal_id,
                        operation=completed,
                    )
                    self._require_original(
                        original, facts=facts, command=command, access=access, operation=completed
                    )
                    assert original is not None
                    return self._result(original, completed)

                if command.expected_access_revision != facts.access_revision:
                    raise StaleRevisionError()
                default = await self._default_repository.get(
                    organization_id=facts.organization_id, project_id=facts.project_id
                )
                if (
                    default.organization_id != facts.organization_id
                    or default.project_id != facts.project_id
                    or default.access_revision != facts.access_revision
                    or default.audience != facts.audience
                ):
                    raise RuntimeError("The loaded upload-default scope or snapshot changed.")
                try:
                    default.replace(
                        audience=command.audience,
                        expected_access_revision=command.expected_access_revision,
                    )
                except ProjectUploadDefaultStaleRevisionError:
                    raise StaleRevisionError() from None
                except InvalidStateTransitionError:
                    raise ConflictError("The Project Access revision cannot advance.") from None

                original = ProjectUploadDefaultRecordDTO(
                    operation.operation_id,
                    facts.organization_id,
                    facts.project_id,
                    access.actor_principal_id,
                    facts.access_revision,
                    default.access_revision,
                    facts.audience,
                    command.audience,
                )
                await self._default_repository.save(
                    default, original=original, fingerprint=fingerprint
                )
                completed = self._require_safe_completed_operation(
                    await self._operation_idempotency.record_completed_result(
                        operation, replay_kind=OperationReplayKind.SAFE_RESULT
                    )
                )
                if completed.operation_id != operation.operation_id:
                    raise ConflictError("Upload-default completion changed its original operation.")
                return self._result(original, completed)
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @staticmethod
    def _require_current_facts(
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        facts: ProjectUploadDefaultFactsDTO | None,
        proposed: UploadAudience | None,
    ) -> ProjectUploadDefaultFactsDTO:
        if facts is None:
            raise ResourceNotFoundError()
        if (
            facts.project_id != project_id
            or facts.action.principal.id != access.actor_principal_id
            or facts.organization_id != facts.action.principal.organization_id
        ):
            raise RuntimeError("Default facts changed the requested actor or scope.")
        RevisionValidation.require(facts.access_revision)
        PrincipalAccessEvaluationService.require_human(
            access=access, principal=facts.action.principal
        )
        ActionAuthorizationService.require_authorization_from_facts(
            access=access, facts=facts.action
        )

        current: set[AccessGroupId] = (
            set(facts.audience.group_ids) if facts.audience is not None else set()
        )
        needed = current.copy()
        if proposed is not None:
            needed.update(proposed.group_ids)
        observed = {group.group_id for group in facts.groups}
        if observed != needed or len(observed) != len(facts.groups):
            raise DependencyUnavailableError("The complete upload audience is unavailable.")
        for group in facts.groups:
            if group.project_id != project_id:
                if group.group_id in current:
                    raise DependencyUnavailableError("The stored upload audience is unavailable.")
                raise ResourceNotFoundError()
            if group.is_manager and not group.is_member:
                raise DependencyUnavailableError("Current group management is incoherent.")
            if not group.is_member or not group.is_manager:
                raise AccessDeniedError()
        return facts

    @staticmethod
    def _require_safe_completed_operation(operation: object) -> CompletedSynchronousOperationDTO:
        if (
            not isinstance(operation, CompletedSynchronousOperationDTO)
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
            or operation.expires_at.utcoffset() is None
        ):
            raise ConflictError("Upload-default recovery requires a safe synchronous original.")
        return operation

    @staticmethod
    def _require_original(
        original: ProjectUploadDefaultRecordDTO | None,
        *,
        facts: ProjectUploadDefaultFactsDTO,
        command: SetProjectUploadDefaultCommand,
        access: AccessContextDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> None:
        if original is None:
            raise ConflictError("The original upload-default result is unavailable.")
        try:
            RevisionValidation.require(original.before_revision)
            RevisionValidation.require(original.access_revision)
            valid = (
                original.operation_id == operation.operation_id
                and original.organization_id == facts.organization_id
                and original.project_id == facts.project_id
                and original.actor_principal_id == access.actor_principal_id
                and original.before_revision == command.expected_access_revision
                and original.audience == command.audience
                and original.access_revision
                == original.before_revision + int(original.before_audience != original.audience)
            )
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise ConflictError("The original upload-default result is incoherent.")

    @staticmethod
    def _result(
        original: ProjectUploadDefaultRecordDTO, operation: CompletedSynchronousOperationDTO
    ) -> ProjectUploadDefaultChangeResultDTO:
        return ProjectUploadDefaultChangeResultDTO(
            ProjectUploadDefaultDTO(
                original.organization_id,
                original.project_id,
                original.access_revision,
                original.audience,
            ),
            operation,
        )
