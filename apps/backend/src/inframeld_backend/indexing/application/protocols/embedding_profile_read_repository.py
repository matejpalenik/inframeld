from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.dtos.embedding_profile_dto import EmbeddingProfileDTO
from inframeld_backend.indexing.domain.value_objects.embedding_profile_id import EmbeddingProfileId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class EmbeddingProfileReadRepository(Protocol):
    """Observe current scope and the exact View assignment in the caller's transaction."""

    @abstractmethod
    async def lock_scope(
        self, access: AccessContextDTO, project_id: ProjectId
    ) -> tuple[InstallationId, ProjectActionFactsDTO] | None: ...

    @abstractmethod
    async def get_visible(
        self, facts: ProjectActionFactsDTO, project_id: ProjectId, profile_id: EmbeddingProfileId
    ) -> EmbeddingProfileDTO | None:
        """Return only a same-scope profile covered by the actor's exact View action."""
        ...

    @abstractmethod
    async def list_visible(
        self,
        facts: ProjectActionFactsDTO,
        project_id: ProjectId,
        after: EmbeddingProfileId | None,
        limit: int,
    ) -> tuple[EmbeddingProfileDTO, ...]:
        """Read bounded ID-ordered rows after applying exact profile View."""
        ...
