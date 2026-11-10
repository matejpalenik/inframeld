from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_upload_default_dto import (
    ProjectUploadDefaultDTO,
)
from inframeld_backend.access.application.queries.get_project_upload_default_query import (
    GetProjectUploadDefaultQuery,
)


class ProjectUploadDefaultReader(Protocol):
    @abstractmethod
    async def get(
        self, *, access: AccessContextDTO, query: GetProjectUploadDefaultQuery
    ) -> ProjectUploadDefaultDTO:
        """Require current human management of the Project default and every saved group."""
        ...
