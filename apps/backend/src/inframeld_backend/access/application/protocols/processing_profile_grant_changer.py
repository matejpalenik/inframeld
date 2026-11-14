from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.change_processing_profile_grant_command import (
    ChangeProcessingProfileGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.processing_profile_grant_result_dto import (
    ProcessingProfileGrantResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class ProcessingProfileGrantChanger(Protocol):
    @abstractmethod
    async def change(
        self,
        access: AccessContextDTO,
        command: ChangeProcessingProfileGrantCommand,
        context: IdempotencyContextDTO,
    ) -> ProcessingProfileGrantResultDTO: ...
