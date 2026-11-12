from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.restore_human_command import RestoreHumanCommand
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_restoration_result_dto import (
    HumanRestorationResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class HumanRestorer(Protocol):
    """Apply the exact currently authorized original lifecycle operation."""

    @abstractmethod
    async def restore(
        self,
        *,
        access: AccessContextDTO,
        command: RestoreHumanCommand,
        context: IdempotencyContextDTO,
    ) -> HumanRestorationResultDTO: ...
