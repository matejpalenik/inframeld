from typing import BinaryIO

from inframeld_backend.access.application.commands.resume_identity_recovery_cleanup_command import (
    ResumeIdentityRecoveryCleanupCommand,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_resumer import (
    IdentityRecoveryCleanupResumer,
)
from inframeld_backend.access.cli.mappers.recovery_maintenance_mapper import (
    RecoveryMaintenanceMapper,
)


class RecoveryMaintenanceCli:
    """Read bounded host input and serialize the owning application operation."""

    def __init__(self, resumer: IdentityRecoveryCleanupResumer) -> None:
        self._resumer = resumer

    @staticmethod
    def read(source: BinaryIO) -> ResumeIdentityRecoveryCleanupCommand:
        return RecoveryMaintenanceMapper.read(source.read(65_537))

    async def execute(self, command: ResumeIdentityRecoveryCleanupCommand) -> dict[str, object]:
        return RecoveryMaintenanceMapper.result(await self._resumer.resume(command=command))
