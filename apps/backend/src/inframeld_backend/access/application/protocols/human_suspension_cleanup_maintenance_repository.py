from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.human_suspension_cleanup_maintenance_command import (
    HumanSuspensionCleanupMaintenanceCommand,
)
from inframeld_backend.access.application.dtos.human_suspension_cleanup_maintenance_result_dto import (
    HumanSuspensionCleanupMaintenanceResultDTO,
)


class HumanSuspensionCleanupMaintenanceRepository(Protocol):
    """Read or continue an exact retained original inside the caller's transaction."""

    @abstractmethod
    async def execute(
        self, *, command: HumanSuspensionCleanupMaintenanceCommand
    ) -> HumanSuspensionCleanupMaintenanceResultDTO: ...
