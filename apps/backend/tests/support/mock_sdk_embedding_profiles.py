"""Return controlled saved profiles through the real HTTP route."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import override
from uuid import UUID

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.commands.create_embedding_profile_command import (
    CreateEmbeddingProfileCommand,
)
from inframeld_backend.indexing.application.dtos.embedding_profile_creation_dto import (
    EmbeddingProfileCreationDTO,
)
from inframeld_backend.indexing.application.dtos.embedding_profile_dto import EmbeddingProfileDTO
from inframeld_backend.indexing.application.dtos.embedding_profile_page_dto import (
    EmbeddingProfilePageDTO,
)
from inframeld_backend.indexing.application.protocols.embedding_profile_creator import (
    EmbeddingProfileCreator,
)
from inframeld_backend.indexing.application.protocols.embedding_profile_reader import (
    EmbeddingProfileReader,
)
from inframeld_backend.indexing.domain.enums.embedding_profile_action import EmbeddingProfileAction
from inframeld_backend.indexing.domain.value_objects.embedding_profile_id import EmbeddingProfileId
from inframeld_backend.indexing.domain.value_objects.vector_index_id import VectorIndexId
from inframeld_backend.indexing.domain.value_objects.vector_layout_id import VectorLayoutId
from inframeld_backend.indexing.domain.value_objects.vector_shard_layout import VectorShardLayout
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.effective_model_settings_dto import (
    EffectiveModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.embedding_model_settings_dto import (
    EmbeddingModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.model_selection_dto import ModelSelectionDTO
from inframeld_backend.shared.application.dtos.reviewed_model_settings_dto import (
    ReviewedModelSettingsDTO,
)
from inframeld_backend.shared.application.enums.embedding_distance import EmbeddingDistance
from inframeld_backend.shared.application.enums.embedding_normalization import (
    EmbeddingNormalization,
)
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.infrastructure.resources.openai_embedding_tokenizer import (
    OpenAIEmbeddingTokenizer,
)

_PROJECT = ProjectId(UUID("00000000-0000-4000-8000-000000000003"))
_ACTOR = PrincipalId(UUID("00000000-0000-4000-8000-000000000001"))
_PROFILE_ID = EmbeddingProfileId(UUID("00000000-0000-4000-8000-000000000249"))
_LAYOUT = VectorShardLayout(
    organization_id=OrganizationId(UUID("00000000-0000-4000-8000-000000000002")),
    project_id=_PROJECT,
    embedding_profile_id=_PROFILE_ID,
    layout_id=VectorLayoutId(UUID("00000000-0000-4000-8000-000000000248")),
    shard_count=2,
)
_PROFILE = EmbeddingProfileDTO(
    name=ResourceName("support-embeddings"),
    display_name=SubmittedDisplayName("Support embeddings"),
    reviewed=ReviewedModelSettingsDTO(
        selection=ModelSelectionDTO(
            _PROJECT,
            ModelConnectionId(UUID("00000000-0000-4000-8000-000000000030")),
            "text-embedding-3-small",
            ModelRole.EMBEDDING,
        ),
        effective=EffectiveModelSettingsDTO(
            8191,
            OpenAIEmbeddingTokenizer.token_bound,
            EmbeddingModelSettingsDTO(
                dimensions=1536,
                normalization=EmbeddingNormalization.L2,
                distance=EmbeddingDistance.COSINE,
                document_prefix="  passage: é\n",
                query_prefix=" query: ",
                expected_provider="openai",
                role=ModelRole.EMBEDDING,
            ),
        ),
        fingerprint="sdk-embedding-profile-fixture",
    ),
    vector_index_id=VectorIndexId(UUID("00000000-0000-4000-8000-000000000247")),
    layout=_LAYOUT,
    shard_names=(_LAYOUT.collection_name(0), _LAYOUT.collection_name(1)),
)


class MockSDKEmbeddingProfiles(EmbeddingProfileCreator, EmbeddingProfileReader):
    @override
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateEmbeddingProfileCommand,
        context: IdempotencyContextDTO,
    ) -> EmbeddingProfileCreationDTO:
        profile = await self.get(access, command.project_id, _PROFILE_ID)
        return EmbeddingProfileCreationDTO(
            profile=replace(
                profile,
                name=command.name,
                display_name=command.display_name,
                reviewed=replace(
                    profile.reviewed, selection=command.selection, effective=command.effective
                ),
            ),
            operation=CompletedSynchronousOperationDTO(
                OperationId("sdk-embedding-profile-create"),
                True,
                OperationReplayKind.SAFE_RESULT,
                datetime(2030, 1, 1, tzinfo=UTC),
            ),
            project_access_revision=8,
            initial_actions=tuple(EmbeddingProfileAction),
            can_grant=True,
        )

    @override
    async def get(
        self, access: AccessContextDTO, project_id: ProjectId, profile_id: EmbeddingProfileId
    ) -> EmbeddingProfileDTO:
        if access.actor_principal_id != _ACTOR:
            raise AccessDeniedError()
        if (project_id, profile_id) != (_PROJECT, _PROFILE_ID):
            raise ResourceNotFoundError()
        return _PROFILE

    @override
    async def list_profiles(
        self, access: AccessContextDTO, project_id: ProjectId, limit: int, cursor: str | None
    ) -> EmbeddingProfilePageDTO:
        return EmbeddingProfilePageDTO((await self.get(access, project_id, _PROFILE_ID),), None)
