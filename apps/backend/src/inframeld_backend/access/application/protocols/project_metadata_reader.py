from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_metadata_dto import ProjectMetadataDTO
from inframeld_backend.access.application.queries.get_project_metadata_query import (
    GetProjectMetadataQuery,
)


class ProjectMetadataReader(Protocol):
    """Read exact Project metadata only after current eligibility and membership checks."""

    @abstractmethod
    async def get(
        self, *, access: AccessContextDTO, query: GetProjectMetadataQuery
    ) -> ProjectMetadataDTO: ...
