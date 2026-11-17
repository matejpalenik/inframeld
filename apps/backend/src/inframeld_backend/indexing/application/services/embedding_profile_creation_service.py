import asyncio
from hashlib import sha256
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
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.policies.model_connection_destination_policy import (
    ModelConnectionDestinationPolicy,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.indexing.application.commands.create_embedding_profile_command import (
    CreateEmbeddingProfileCommand,
)
from inframeld_backend.indexing.application.dtos.embedding_profile_creation_dto import (
    EmbeddingProfileCreationDTO,
)
from inframeld_backend.indexing.application.dtos.embedding_profile_creation_facts_dto import (
    EmbeddingProfileCreationFactsDTO,
)
from inframeld_backend.indexing.application.dtos.embedding_profile_dto import EmbeddingProfileDTO
from inframeld_backend.indexing.application.protocols.embedding_profile_creation_repository import (
    EmbeddingProfileCreationRepository,
)
from inframeld_backend.indexing.application.protocols.embedding_profile_creator import (
    EmbeddingProfileCreator,
)
from inframeld_backend.indexing.domain.enums.embedding_profile_action import EmbeddingProfileAction
from inframeld_backend.indexing.domain.value_objects.embedding_profile_id import EmbeddingProfileId
from inframeld_backend.indexing.domain.value_objects.vector_index_id import VectorIndexId
from inframeld_backend.indexing.domain.value_objects.vector_layout_id import VectorLayoutId
from inframeld_backend.indexing.domain.value_objects.vector_shard_layout import VectorShardLayout
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.embedding_model_settings_dto import (
    EmbeddingModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.reviewed_model_settings_dto import (
    ReviewedModelSettingsDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
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
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation

_INITIAL_ACTIONS = (EmbeddingProfileAction.VIEW, EmbeddingProfileAction.USE)
_SETTINGS_DOMAIN = b"inframeld:embedding-profile-settings:v1\x00"


class EmbeddingProfileCreationService(EmbeddingProfileCreator):
    """Create the immutable profile, original layout and initial creator assignments."""

    def __init__(
        self,
        repository: EmbeddingProfileCreationRepository,
        idempotency: OperationIdempotency,
        fingerprints: RequestFingerprintService,
        *,
        transactions: TransactionManager,
        official_destinations: ModelConnectionDestinationPolicy | None,
    ) -> None:
        self._repository = repository
        self._idempotency = idempotency
        self._fingerprints = fingerprints
        self._transactions = transactions
        self._official_destinations = official_destinations

    @override
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateEmbeddingProfileCommand,
        context: IdempotencyContextDTO,
    ) -> EmbeddingProfileCreationDTO:
        route = f"/v1/projects/{command.project_id.value}/embedding-profiles"
        if context.method is not HttpMethod.POST or context.requested_route != route:
            raise RuntimeError("Embedding Profile creation has a different operation route.")

        reviewed, fingerprint = self._prepare_settings(command)
        try:
            async with asyncio.timeout(5), self._transactions.begin():
                return await self._create_or_replay(access, command, context, reviewed, fingerprint)
        except TimeoutError:
            raise DependencyUnavailableError() from None

    async def _create_or_replay(
        self,
        access: AccessContextDTO,
        command: CreateEmbeddingProfileCommand,
        context: IdempotencyContextDTO,
        reviewed: ReviewedModelSettingsDTO,
        fingerprint: RequestFingerprint,
    ) -> EmbeddingProfileCreationDTO:
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
            raise RuntimeError("Embedding Profile creation changed the actor or Project.")
        PrincipalAccessEvaluationService.require_human(access=access, principal=principal)
        ActionAuthorizationService.require_authorization_from_facts(
            access=access, facts=facts.action
        )

        operation = await self._idempotency.reserve_or_recover(
            context=context,
            access=access,
            authorization=facts,
            fingerprint=fingerprint,
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
            lookup_authority=OperationLookupAuthority(
                OperationLookupAuthorityFamily.PROJECT_ACTION_USE,
                ActionId(ProjectAction.CREATE_EMBEDDING_PROFILES.value),
            ),
        )
        if not isinstance(operation, NewOperationReservationDTO):
            return await self._original(
                access, facts, command, reviewed, self._safe_completion(operation, created=False)
            )

        RevisionValidation.require(facts.access_revision)
        if facts.access_revision == RevisionValidation.MAX_VALUE:
            raise ConflictError("The Project access revision is exhausted.")
        current_access = await self._repository.lock_live_selection(
            facts=facts, connection_id=reviewed.selection.connection_id
        )
        if current_access is None:
            raise ResourceNotFoundError("The selected Model Connection is not available.")
        if self._official_destinations is not None and (
            current_access.provider is not ModelConnectionProvider.OPENAI
            or not self._official_destinations.permits(
                provider=current_access.provider,
                base_url=current_access.base_url,
                api_version=current_access.api_version,
                authentication=current_access.authentication,
            )
        ):
            raise ConflictError("Select an approved official OpenAI Model Connection.")

        layout = VectorShardLayout(
            organization_id=facts.organization_id,
            project_id=facts.project_id,
            embedding_profile_id=EmbeddingProfileId(uuid4()),
            layout_id=VectorLayoutId(uuid4()),
            shard_count=2,
        )
        profile = EmbeddingProfileDTO(
            name=command.name,
            display_name=command.display_name,
            reviewed=reviewed,
            vector_index_id=VectorIndexId(uuid4()),
            layout=layout,
            shard_names=(layout.collection_name(0), layout.collection_name(1)),
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
            raise RuntimeError("Embedding Profile creation changed the original operation ID.")
        return EmbeddingProfileCreationDTO(
            profile=profile,
            operation=completed,
            project_access_revision=facts.access_revision + 1,
            initial_actions=_INITIAL_ACTIONS,
            can_grant=True,
        )

    async def _original(
        self,
        access: AccessContextDTO,
        facts: EmbeddingProfileCreationFactsDTO,
        command: CreateEmbeddingProfileCommand,
        reviewed: ReviewedModelSettingsDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> EmbeddingProfileCreationDTO:
        original = await self._repository.original(access=access, facts=facts, operation=operation)
        profile = original.profile
        if (
            original.operation != operation
            or original.initial_actions != _INITIAL_ACTIONS
            or original.can_grant is not True
            or type(original.project_access_revision) is not int
            or not 0 < original.project_access_revision <= facts.access_revision
            or profile.layout.organization_id != facts.organization_id
            or profile.layout.project_id != facts.project_id
            or profile.name != command.name
            or profile.display_name != command.display_name
            or profile.reviewed != reviewed
            or not profile.has_coherent_layout()
        ):
            raise ConflictError("The original Embedding Profile creation result is incoherent.")

        return original

    def _prepare_settings(
        self, command: CreateEmbeddingProfileCommand
    ) -> tuple[ReviewedModelSettingsDTO, RequestFingerprint]:
        selection = command.selection
        effective = command.effective
        embedding = effective.settings
        if (
            selection.project_id != command.project_id
            or selection.role is not ModelRole.EMBEDDING
            or not isinstance(embedding, EmbeddingModelSettingsDTO)
            or embedding.role is not ModelRole.EMBEDDING
        ):
            raise InvalidInputError("Select an embedding model in the requested Project.")
        if not 1 <= embedding.dimensions <= 1536:
            raise InvalidInputError("An Embedding Profile requires 1 to 1536 dimensions.")

        # The same effective fields define model meaning and the settings part of the create request.
        settings = {
            "projectId": str(selection.project_id.value),
            "connectionId": str(selection.connection_id.value),
            "role": selection.role.value,
            "model": selection.model,
            "provider": embedding.expected_provider,
            "modelRevision": embedding.expected_model_revision,
            "dimensions": embedding.dimensions,
            "normalization": embedding.normalization.value,
            "distance": embedding.distance.value,
            "documentPrefix": embedding.document_prefix,
            "queryPrefix": embedding.query_prefix,
            "contextTokens": effective.context_tokens,
            "tokenBoundKind": effective.token_bound.kind.value,
            "tokenBoundImplementation": effective.token_bound.implementation,
            "tokenBoundRevision": effective.token_bound.revision,
        }
        canonical_settings = dumps(settings, sort_keys=True, separators=(",", ":")).encode()
        reviewed = ReviewedModelSettingsDTO(
            selection=selection,
            effective=effective,
            fingerprint=sha256(_SETTINGS_DOMAIN + canonical_settings).hexdigest(),
        )
        request = dumps(
            {
                "name": command.name.value,
                "displayName": command.display_name.value,
                "settings": settings,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        fingerprint = self._fingerprints.fingerprint(
            purpose="indexing.embedding-profile.create:v1", canonical_request=request
        )
        return reviewed, fingerprint

    @staticmethod
    def _safe_completion(operation: object, *, created: bool) -> CompletedSynchronousOperationDTO:
        if (
            not isinstance(operation, CompletedSynchronousOperationDTO)
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
            or operation.created is not created
        ):
            raise ConflictError("Embedding Profile creation has no safe completed result.")
        return operation
