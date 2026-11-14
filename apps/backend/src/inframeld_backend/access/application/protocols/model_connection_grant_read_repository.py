from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_grant_facts_dto import (
    ModelConnectionGrantFactsDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_item_dto import (
    ModelConnectionGrantItemDTO,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId


class ModelConnectionGrantReadRepository(Protocol):
    @abstractmethod
    async def lock_for_read(
        self,
        access: AccessContextDTO,
        connection_id: ModelConnectionId,
        action: ModelConnectionAction,
    ) -> ModelConnectionGrantFactsDTO | None: ...

    @abstractmethod
    async def list_assignments(
        self,
        facts: ModelConnectionGrantFactsDTO,
        after: PrincipalId | None,
        limit: int,
    ) -> tuple[ModelConnectionGrantItemDTO, ...]: ...
