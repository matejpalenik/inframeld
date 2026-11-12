from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.restore_human_command import RestoreHumanCommand
from inframeld_backend.access.application.commands.suspend_human_command import SuspendHumanCommand
from inframeld_backend.access.application.dtos.human_lifecycle_facts_dto import (
    HumanLifecycleFactsDTO,
)
from inframeld_backend.access.application.dtos.human_restoration_result_dto import (
    HumanRestorationResultDTO,
)
from inframeld_backend.access.application.dtos.human_suspension_result_dto import (
    HumanSuspensionResultDTO,
)
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


class HumanLifecycleResultReader(Protocol):
    """Recover immutable safe originals only after current exact authority."""

    @abstractmethod
    async def suspension_original(
        self,
        *,
        facts: HumanLifecycleFactsDTO,
        command: SuspendHumanCommand,
        operation: AcceptedAsyncOperationDTO,
    ) -> HumanSuspensionResultDTO | None: ...

    @abstractmethod
    async def restoration_original(
        self,
        *,
        facts: HumanLifecycleFactsDTO,
        command: RestoreHumanCommand,
        operation: CompletedSynchronousOperationDTO,
    ) -> HumanRestorationResultDTO | None: ...
