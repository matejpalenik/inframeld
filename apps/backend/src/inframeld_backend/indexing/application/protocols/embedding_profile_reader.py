from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.dtos.embedding_profile_dto import EmbeddingProfileDTO
from inframeld_backend.indexing.application.dtos.embedding_profile_page_dto import (
    EmbeddingProfilePageDTO,
)
from inframeld_backend.indexing.domain.value_objects.embedding_profile_id import EmbeddingProfileId


class EmbeddingProfileReader(Protocol):
    @abstractmethod
    async def get(
        self, access: AccessContextDTO, project_id: ProjectId, profile_id: EmbeddingProfileId
    ) -> EmbeddingProfileDTO: ...

    @abstractmethod
    async def list_profiles(
        self, access: AccessContextDTO, project_id: ProjectId, limit: int, cursor: str | None
    ) -> EmbeddingProfilePageDTO: ...
