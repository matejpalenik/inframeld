import asyncio

from inframeld_backend.access.application.commands.human_suspension_cleanup_maintenance_command import (
    HumanSuspensionCleanupMaintenanceCommand,
)
from inframeld_backend.access.application.dtos.human_suspension_cleanup_maintenance_result_dto import (
    HumanSuspensionCleanupMaintenanceResultDTO,
)
from inframeld_backend.access.application.protocols.human_suspension_cleanup_maintenance_repository import (
    HumanSuspensionCleanupMaintenanceRepository,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager


class HumanSuspensionCleanupMaintenanceService:
    """Own the protected inspection or continuation transaction."""

    def __init__(
        self,
        transaction_manager: TransactionManager,
        repository: HumanSuspensionCleanupMaintenanceRepository,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._repository = repository

    async def execute(
        self, *, command: HumanSuspensionCleanupMaintenanceCommand
    ) -> HumanSuspensionCleanupMaintenanceResultDTO:
        try:
            async with asyncio.timeout(5):
                async with self._transaction_manager.begin():
                    return await self._repository.execute(command=command)
        except TimeoutError:
            raise DependencyUnavailableError(
                "Suspension cleanup maintenance exceeded its database deadline."
            ) from None
