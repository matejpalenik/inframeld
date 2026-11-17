from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from tests.support.mock_project_metadata import (
    ACCESS,
    ORGANIZATION_ID,
    PROJECT_ID,
    MockTransactions,
)

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.dtos.embedding_profile_dto import EmbeddingProfileDTO
from inframeld_backend.indexing.application.protocols.embedding_profile_read_repository import (
    EmbeddingProfileReadRepository,
)
from inframeld_backend.indexing.application.services.embedding_profile_read_service import (
    EmbeddingProfileReadService,
)
from inframeld_backend.indexing.domain.value_objects.embedding_profile_id import EmbeddingProfileId
from inframeld_backend.indexing.domain.value_objects.vector_index_id import VectorIndexId
from inframeld_backend.indexing.domain.value_objects.vector_layout_id import VectorLayoutId
from inframeld_backend.indexing.domain.value_objects.vector_shard_layout import VectorShardLayout
from inframeld_backend.shared.application.dtos.effective_model_settings_dto import (
    EffectiveModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.embedding_model_settings_dto import (
    EmbeddingModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.model_selection_dto import ModelSelectionDTO
from inframeld_backend.shared.application.dtos.model_token_bound_dto import ModelTokenBoundDTO
from inframeld_backend.shared.application.dtos.reviewed_model_settings_dto import (
    ReviewedModelSettingsDTO,
)
from inframeld_backend.shared.application.enums.embedding_distance import EmbeddingDistance
from inframeld_backend.shared.application.enums.embedding_normalization import (
    EmbeddingNormalization,
)
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.enums.model_token_bound_kind import ModelTokenBoundKind
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)

_PROFILE_ID = EmbeddingProfileId(UUID(int=4))
_LAYOUT = VectorShardLayout(
    organization_id=ORGANIZATION_ID,
    project_id=PROJECT_ID,
    embedding_profile_id=_PROFILE_ID,
    layout_id=VectorLayoutId(UUID(int=5)),
    shard_count=2,
)
_PROFILE = EmbeddingProfileDTO(
    name=ResourceName("support-embeddings"),
    display_name=SubmittedDisplayName("Support embeddings"),
    reviewed=ReviewedModelSettingsDTO(
        selection=ModelSelectionDTO(
            PROJECT_ID, ModelConnectionId(UUID(int=6)), "exact-model", ModelRole.EMBEDDING
        ),
        effective=EffectiveModelSettingsDTO(
            8192,
            ModelTokenBoundDTO(ModelTokenBoundKind.EXACT, "fixture-tokenizer", "fixture-revision"),
            EmbeddingModelSettingsDTO(
                dimensions=1536,
                normalization=EmbeddingNormalization.L2,
                distance=EmbeddingDistance.COSINE,
                document_prefix="",
                query_prefix="",
                expected_provider="openai",
                role=ModelRole.EMBEDDING,
            ),
        ),
        fingerprint="saved-fingerprint",
    ),
    vector_index_id=VectorIndexId(UUID(int=7)),
    layout=_LAYOUT,
    shard_names=(_LAYOUT.collection_name(0), _LAYOUT.collection_name(1)),
)
_FACTS = ProjectActionFactsDTO(
    Principal(
        ACCESS.actor_principal_id, ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
    ),
    False,
    HumanCredentialFactsDTO(True, HumanCredentialVersion(1)),
    ProjectStatus.ACTIVE,
    True,
    False,
)


class MockEmbeddingProfileReadRepository(EmbeddingProfileReadRepository):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.facts = _FACTS
        self.visible: EmbeddingProfileDTO | None = _PROFILE
        self.installation = InstallationId(UUID(int=11))

    @override
    async def lock_scope(
        self, access: AccessContextDTO, project_id: ProjectId
    ) -> tuple[InstallationId, ProjectActionFactsDTO]:
        assert access == ACCESS and project_id == PROJECT_ID
        self.events.append("scope")
        return self.installation, self.facts

    @override
    async def get_visible(
        self, facts: ProjectActionFactsDTO, project_id: ProjectId, profile_id: EmbeddingProfileId
    ) -> EmbeddingProfileDTO | None:
        assert facts == self.facts and (project_id, profile_id) == (PROJECT_ID, _PROFILE_ID)
        self.events.append("view")
        return self.visible

    @override
    async def list_visible(
        self,
        facts: ProjectActionFactsDTO,
        project_id: ProjectId,
        after: EmbeddingProfileId | None,
        limit: int,
    ) -> tuple[EmbeddingProfileDTO, ...]:
        assert facts == self.facts and project_id == PROJECT_ID and limit == 2
        self.events.append("list")
        layout = replace(_LAYOUT, embedding_profile_id=EmbeddingProfileId(UUID(int=5)))
        second = replace(
            _PROFILE,
            layout=layout,
            shard_names=(layout.collection_name(0), layout.collection_name(1)),
        )
        return (_PROFILE, second) if after is None else (second,)


@pytest.mark.asyncio
async def test_list_exposes_visible_profiles_in_a_bounded_page() -> None:
    events: list[str] = []
    repository = MockEmbeddingProfileReadRepository(events)
    service = EmbeddingProfileReadService(MockTransactions(events), repository)

    page = await service.list_profiles(ACCESS, PROJECT_ID, 1, None)

    assert page.items == (_PROFILE,)
    assert page.next_cursor is not None
    assert events == ["begin", "scope", "list", "commit"]
    next_page = await service.list_profiles(ACCESS, PROJECT_ID, 1, page.next_cursor)
    assert next_page.items[0].layout.embedding_profile_id != _PROFILE_ID
    assert next_page.next_cursor is None

    repository.installation = InstallationId(UUID(int=12))
    with pytest.raises(InvalidInputError):
        await service.list_profiles(ACCESS, PROJECT_ID, 1, page.next_cursor)
    assert events[-3:] == ["begin", "scope", "rollback"]


@pytest.mark.asyncio
async def test_returns_only_the_result_of_the_exact_view_lookup() -> None:
    events: list[str] = []
    repository = MockEmbeddingProfileReadRepository(events)
    service = EmbeddingProfileReadService(MockTransactions(events), repository)

    profile = await service.get(ACCESS, PROJECT_ID, _PROFILE_ID)

    assert profile == _PROFILE
    assert events == ["begin", "scope", "view", "commit"]

    events.clear()
    repository.visible = None
    with pytest.raises(ResourceNotFoundError):
        await service.get(ACCESS, PROJECT_ID, _PROFILE_ID)

    assert events == ["begin", "scope", "view", "rollback"]


@pytest.mark.asyncio
async def test_stale_credential_stops_before_profile_lookup() -> None:
    events: list[str] = []
    repository = MockEmbeddingProfileReadRepository(events)
    repository.facts = replace(
        _FACTS, oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(2))
    )
    service = EmbeddingProfileReadService(MockTransactions(events), repository)

    with pytest.raises(AuthenticationRequiredError):
        await service.get(ACCESS, PROJECT_ID, _PROFILE_ID)

    assert events == ["begin", "scope", "rollback"]


@pytest.mark.asyncio
async def test_cannot_disclose_profile_outside_the_requested_project() -> None:
    events: list[str] = []
    repository = MockEmbeddingProfileReadRepository(events)
    other_project = ProjectId(UUID(int=8))
    layout = replace(_LAYOUT, project_id=other_project)
    reviewed = replace(
        _PROFILE.reviewed, selection=replace(_PROFILE.reviewed.selection, project_id=other_project)
    )
    repository.visible = replace(
        _PROFILE,
        reviewed=reviewed,
        layout=layout,
        shard_names=(layout.collection_name(0), layout.collection_name(1)),
    )
    service = EmbeddingProfileReadService(MockTransactions(events), repository)

    with pytest.raises(RuntimeError, match="exact target"):
        await service.get(ACCESS, PROJECT_ID, _PROFILE_ID)

    assert events == ["begin", "scope", "view", "rollback"]
