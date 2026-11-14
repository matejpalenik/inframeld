from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_grants_page_dto import (
    ModelConnectionGrantsPageDTO,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId


class ModelConnectionGrantsReader(Protocol):
    @abstractmethod
    async def list_grants(
        self,
        access: AccessContextDTO,
        connection_id: ModelConnectionId,
        action: ModelConnectionAction,
        limit: int,
        cursor: str | None,
    ) -> ModelConnectionGrantsPageDTO: ...
