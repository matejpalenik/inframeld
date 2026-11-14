from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.create_model_connection_command import (
    CreateModelConnectionCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_creation_dto import (
    ModelConnectionCreationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class ModelConnectionCreator(Protocol):
    @abstractmethod
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateModelConnectionCommand,
        context: IdempotencyContextDTO,
    ) -> ModelConnectionCreationDTO: ...
