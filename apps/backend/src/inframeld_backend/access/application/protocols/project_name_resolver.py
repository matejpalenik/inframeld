from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_metadata_dto import ProjectMetadataDTO
from inframeld_backend.access.application.queries.resolve_project_name_query import (
    ResolveProjectNameQuery,
)


class ProjectNameResolver(Protocol):
    """Resolve only an exact Project name, checking current Access before disclosure."""

    @abstractmethod
    async def resolve(
        self, *, access: AccessContextDTO, query: ResolveProjectNameQuery
    ) -> ProjectMetadataDTO: ...
