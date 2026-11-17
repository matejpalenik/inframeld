from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.commands.create_embedding_profile_command import (
    CreateEmbeddingProfileCommand,
)
from inframeld_backend.indexing.application.dtos.embedding_profile_creation_dto import (
    EmbeddingProfileCreationDTO,
)
from inframeld_backend.indexing.application.dtos.embedding_profile_dto import EmbeddingProfileDTO
from inframeld_backend.indexing.http.requests.embedding_profile_creation_request import (
    EmbeddingProfileCreationRequest,
)
from inframeld_backend.indexing.http.responses.embedding_profile_creation_response import (
    EmbeddingProfileCreationResponse,
)
from inframeld_backend.indexing.http.responses.embedding_profile_definition_response import (
    EmbeddingProfileDefinitionResponse,
)
from inframeld_backend.indexing.http.responses.embedding_profile_grant_target_response import (
    EmbeddingProfileGrantTargetResponse,
)
from inframeld_backend.indexing.http.responses.embedding_profile_response import (
    EmbeddingProfileResponse,
)
from inframeld_backend.indexing.http.responses.embedding_profile_token_bound_response import (
    EmbeddingProfileTokenBoundResponse,
)
from inframeld_backend.indexing.http.responses.initial_embedding_profile_grant_response import (
    InitialEmbeddingProfileGrantResponse,
)
from inframeld_backend.shared.application.dtos.effective_model_settings_dto import (
    EffectiveModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.embedding_model_settings_dto import (
    EmbeddingModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.model_selection_dto import ModelSelectionDTO
from inframeld_backend.shared.application.dtos.model_token_bound_dto import ModelTokenBoundDTO
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


class EmbeddingProfileMapper:
    @staticmethod
    def command(
        project_id: ProjectId,
        body: EmbeddingProfileCreationRequest,
        token_bound: ModelTokenBoundDTO,
    ) -> CreateEmbeddingProfileCommand:
        definition = body.definition
        return CreateEmbeddingProfileCommand(
            project_id=project_id,
            name=ResourceName(body.name),
            display_name=SubmittedDisplayName(body.display_name),
            selection=ModelSelectionDTO(
                project_id,
                ModelConnectionId(definition.model_connection_id),
                definition.model,
                ModelRole.EMBEDDING,
            ),
            effective=EffectiveModelSettingsDTO(
                definition.context_tokens,
                token_bound,
                EmbeddingModelSettingsDTO(
                    dimensions=definition.dimensions,
                    normalization=definition.normalization,
                    distance=definition.distance,
                    document_prefix=definition.document_prefix,
                    query_prefix=definition.query_prefix,
                    expected_provider=ModelConnectionProvider.OPENAI.value,
                    role=ModelRole.EMBEDDING,
                ),
            ),
        )

    @staticmethod
    def profile(profile: EmbeddingProfileDTO) -> EmbeddingProfileResponse:
        reviewed = profile.reviewed
        effective = reviewed.effective
        settings = effective.settings
        if not isinstance(settings, EmbeddingModelSettingsDTO):
            raise RuntimeError("The profile has no saved embedding settings.")
        return EmbeddingProfileResponse(
            project_id=profile.layout.project_id.value,
            embedding_profile_id=profile.layout.embedding_profile_id.value,
            name=profile.name.value,
            display_name=profile.display_name.value,
            definition=EmbeddingProfileDefinitionResponse(
                model_connection_id=reviewed.selection.connection_id.value,
                model=reviewed.selection.model,
                role=settings.role,
                dimensions=settings.dimensions,
                normalization=settings.normalization,
                distance=settings.distance,
                document_prefix=settings.document_prefix,
                query_prefix=settings.query_prefix,
                context_tokens=effective.context_tokens,
                expected_provider=settings.expected_provider,
                expected_model_revision=settings.expected_model_revision,
                token_bound=EmbeddingProfileTokenBoundResponse(
                    kind=effective.token_bound.kind,
                    implementation=effective.token_bound.implementation,
                    revision=effective.token_bound.revision,
                ),
            ),
            vector_index_id=profile.vector_index_id.value,
            vector_layout_id=profile.layout.layout_id.value,
            placement_version=profile.layout.version,
            shard_count=profile.layout.shard_count,
        )

    @staticmethod
    def creation(result: EmbeddingProfileCreationDTO) -> EmbeddingProfileCreationResponse:
        target = EmbeddingProfileGrantTargetResponse(
            kind="embedding-profile",
            embedding_profile_id=result.profile.layout.embedding_profile_id.value,
        )
        return EmbeddingProfileCreationResponse(
            profile=EmbeddingProfileMapper.profile(result.profile),
            operation_id=result.operation.operation_id.value,
            idempotency_expires_at=result.operation.expires_at,
            project_access_revision=result.project_access_revision,
            initial_grants=tuple(
                InitialEmbeddingProfileGrantResponse(
                    target=target, action_id=action, can_grant=result.can_grant
                )
                for action in result.initial_actions
            ),
        )
