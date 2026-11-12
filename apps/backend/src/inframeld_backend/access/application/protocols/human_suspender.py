from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.suspend_human_command import SuspendHumanCommand
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_suspension_result_dto import (
    HumanSuspensionResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.value_objects.request_id import RequestId


class HumanSuspender(Protocol):
    """Apply the exact currently authorized original lifecycle operation."""

    @abstractmethod
    async def suspend(
        self,
        *,
        access: AccessContextDTO,
        command: SuspendHumanCommand,
        context: IdempotencyContextDTO,
        request_id: RequestId,
    ) -> HumanSuspensionResultDTO: ...
