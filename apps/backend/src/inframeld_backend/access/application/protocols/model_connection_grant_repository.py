from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.change_model_connection_grant_command import (
    ChangeModelConnectionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_grant_facts_dto import (
    ModelConnectionGrantFactsDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_result_dto import (
    ModelConnectionGrantResultDTO,
)
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class ModelConnectionGrantRepository(Protocol):
    @abstractmethod
    async def lock_for_change(
        self, access: AccessContextDTO, command: ChangeModelConnectionGrantCommand
    ) -> ModelConnectionGrantFactsDTO | None: ...

    @abstractmethod
    async def original(
        self, facts: ModelConnectionGrantFactsDTO, operation: CompletedSynchronousOperationDTO
    ) -> ModelConnectionGrantResultDTO: ...

    @abstractmethod
    async def save_change(
        self,
        facts: ModelConnectionGrantFactsDTO,
        recipient_id: PrincipalId,
        after: ActionGrantState,
        operation_id: OperationId,
    ) -> None: ...

    @abstractmethod
    async def save_result(
        self, facts: ModelConnectionGrantFactsDTO, result: ModelConnectionGrantResultDTO
    ) -> None: ...
