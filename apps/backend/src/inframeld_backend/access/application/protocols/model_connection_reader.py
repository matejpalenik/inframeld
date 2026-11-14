from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_dto import ModelConnectionDTO
from inframeld_backend.access.application.dtos.model_connections_page_dto import (
    ModelConnectionsPageDTO,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId


class ModelConnectionReader(Protocol):
    @abstractmethod
    async def get(
        self, access: AccessContextDTO, project_id: ProjectId, connection_id: ModelConnectionId
    ) -> ModelConnectionDTO: ...

    @abstractmethod
    async def list_connections(
        self, access: AccessContextDTO, project_id: ProjectId, limit: int, cursor: str | None
    ) -> ModelConnectionsPageDTO: ...

    @abstractmethod
    async def list_usage(
        self,
        access: AccessContextDTO,
        project_id: ProjectId,
        connection_id: ModelConnectionId,
        limit: int,
        cursor: str | None,
    ) -> None:
        """Authorize the exact connection. V1 currently has no installed consumer owners."""
        ...
