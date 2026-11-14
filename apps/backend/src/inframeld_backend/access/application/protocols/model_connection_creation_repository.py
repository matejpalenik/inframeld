from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_creation_dto import (
    ModelConnectionCreationDTO,
)
from inframeld_backend.access.application.dtos.model_connection_creation_facts_dto import (
    ModelConnectionCreationFactsDTO,
)
from inframeld_backend.access.application.dtos.model_connection_dto import ModelConnectionDTO
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class ModelConnectionCreationRepository(Protocol):
    """Keep original receipts and the creator grant transaction under the same Project turn."""

    @abstractmethod
    async def lock_for_creation(
        self, access: AccessContextDTO, project_id: ProjectId
    ) -> ModelConnectionCreationFactsDTO | None: ...

    @abstractmethod
    async def original(
        self,
        access: AccessContextDTO,
        facts: ModelConnectionCreationFactsDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> ModelConnectionCreationDTO: ...

    @abstractmethod
    async def save(
        self,
        access: AccessContextDTO,
        facts: ModelConnectionCreationFactsDTO,
        operation_id: OperationId,
        connection: ModelConnectionDTO,
        initial_actions: tuple[ModelConnectionAction, ...],
    ) -> None: ...
