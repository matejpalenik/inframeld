import asyncio
from json import dumps
from typing import override
from uuid import uuid4

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.indexing.application.commands.create_processing_profile_command import (
    CreateProcessingProfileCommand,
)
from inframeld_backend.indexing.application.dtos.processing_profile_creation_dto import (
    ProcessingProfileCreationDTO,
)
from inframeld_backend.indexing.application.dtos.processing_profile_dto import ProcessingProfileDTO
from inframeld_backend.indexing.application.protocols.processing_profile_creation_repository import (
    ProcessingProfileCreationRepository,
)
from inframeld_backend.indexing.application.protocols.processing_profile_creator import (
    ProcessingProfileCreator,
)
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
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
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
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
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation

_INITIAL_ACTIONS = (ProcessingProfileAction.VIEW, ProcessingProfileAction.USE)


class ProcessingProfileCreationService(ProcessingProfileCreator):
    """Create a Working Processing Profile with its grants and original result."""

    def __init__(
        self,
        repository: ProcessingProfileCreationRepository,
        idempotency: OperationIdempotency,
        fingerprints: RequestFingerprintService,
        *,
        transactions: TransactionManager,
    ) -> None:
        self._repository = repository
        self._idempotency = idempotency
        self._fingerprints = fingerprints
        self._transactions = transactions

    @override
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateProcessingProfileCommand,
        context: IdempotencyContextDTO,
    ) -> ProcessingProfileCreationDTO:
        try:
            async with asyncio.timeout(5), self._transactions.begin():
                return await self.create_in_transaction(
                    access=access, command=command, context=context
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None

    async def create_in_transaction(
        self,
        *,
        access: AccessContextDTO,
        command: CreateProcessingProfileCommand,
        context: IdempotencyContextDTO,
    ) -> ProcessingProfileCreationDTO:
        """Reserve and save under the caller's deadline and rollback boundary."""
        route = f"/v1/projects/{command.project_id.value}/processing-profiles"
        if context.method is not HttpMethod.POST or context.requested_route != route:
            raise RuntimeError("Processing Profile creation has a different operation route.")

        facts = await self._repository.lock_for_creation(
            access=access, project_id=command.project_id
        )
        if facts is None:
            raise ResourceNotFoundError()
        principal = facts.action.principal
        if (
            facts.project_id != command.project_id
            or principal.id != access.actor_principal_id
            or principal.organization_id != facts.organization_id
        ):
            raise RuntimeError("Processing Profile creation changed the actor or Project.")
        PrincipalAccessEvaluationService.require_human(access=access, principal=principal)
        ActionAuthorizationService.require_authorization_from_facts(
            access=access, facts=facts.action
        )

        operation = await self._idempotency.reserve_or_recover(
            context=context,
            access=access,
            authorization=facts,
            fingerprint=self._fingerprint(command),
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
            lookup_authority=OperationLookupAuthority(
                OperationLookupAuthorityFamily.PROJECT_ACTION_USE,
                ActionId(ProjectAction.CREATE_PROCESSING_PROFILES.value),
            ),
        )
        if not isinstance(operation, NewOperationReservationDTO):
            completed = self._safe_completion(operation, created=False)
            original = await self._repository.original(
                access=access, facts=facts, operation=completed
            )
            if (
                original.operation != completed
                or original.profile.project_id != command.project_id
                or original.profile.name != command.name
                or original.profile.display_name != command.display_name
                or original.profile.definition != command.definition
                or original.initial_actions != _INITIAL_ACTIONS
                or original.can_grant is not True
            ):
                raise ConflictError(
                    "The original Processing Profile creation result is incoherent."
                )
            return original

        RevisionValidation.require(facts.access_revision)
        if facts.access_revision == RevisionValidation.MAX_VALUE:
            raise ConflictError("The Project access revision is exhausted.")
        profile = ProcessingProfileDTO(
            project_id=command.project_id,
            id=ProcessingProfileId(uuid4()),
            name=command.name,
            display_name=command.display_name,
            definition=command.definition,
        )
        await self._repository.save(
            access=access,
            facts=facts,
            operation_id=operation.operation_id,
            profile=profile,
            initial_actions=_INITIAL_ACTIONS,
            can_grant=True,
        )
        completed = self._safe_completion(
            await self._idempotency.record_completed_result(
                operation, replay_kind=OperationReplayKind.SAFE_RESULT
            ),
            created=True,
        )
        if completed.operation_id != operation.operation_id:
            raise RuntimeError("Processing Profile creation changed the original operation ID.")
        return ProcessingProfileCreationDTO(
            profile=profile,
            operation=completed,
            project_access_revision=facts.access_revision + 1,
            initial_actions=_INITIAL_ACTIONS,
            can_grant=True,
        )

    def _fingerprint(self, command: CreateProcessingProfileCommand) -> RequestFingerprint:
        definition = command.definition
        canonical_request = dumps(
            {
                "projectId": str(command.project_id.value),
                "name": command.name.value,
                "displayName": command.display_name.value,
                "doclingSlimVersion": definition.docling_slim_version,
                "doclingCoreVersion": definition.docling_core_version,
                "assetManifestSha256": definition.asset_manifest_sha256,
                "maxContentTokens": definition.max_content_tokens,
                "mergePeers": definition.merge_peers,
                "repeatTableHeader": definition.repeat_table_header,
                "ocrEnabled": definition.ocr_enabled,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return self._fingerprints.fingerprint(
            purpose="indexing.processing-profile.create:v1", canonical_request=canonical_request
        )

    @staticmethod
    def _safe_completion(operation: object, *, created: bool) -> CompletedSynchronousOperationDTO:
        if (
            not isinstance(operation, CompletedSynchronousOperationDTO)
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
            or operation.created is not created
        ):
            raise ConflictError("Processing Profile creation has no safe completed result.")
        return operation
