from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.change_model_connection_grant_command import (
    ChangeModelConnectionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_grant_result_dto import (
    ModelConnectionGrantResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class ModelConnectionGrantChanger(Protocol):
    @abstractmethod
    async def change(
        self,
        access: AccessContextDTO,
        command: ChangeModelConnectionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> ModelConnectionGrantResultDTO: ...
