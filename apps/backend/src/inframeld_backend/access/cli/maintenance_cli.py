from typing import BinaryIO

from inframeld_backend.access.application.commands.bootstrap_first_administrator_command import (
    BootstrapFirstAdministratorCommand,
)
from inframeld_backend.access.application.commands.repair_stranded_authority_command import (
    RepairStrandedAuthorityCommand,
)
from inframeld_backend.access.application.commands.resume_identity_recovery_cleanup_command import (
    ResumeIdentityRecoveryCleanupCommand,
)
from inframeld_backend.access.cli.errors.stranded_authority_maintenance_input_error import (
    StrandedAuthorityMaintenanceInputError,
)
from inframeld_backend.access.cli.mappers.first_administrator_bootstrap_mapper import (
    FirstAdministratorBootstrapMapper,
)
from inframeld_backend.access.cli.mappers.maintenance_input_mapper import MaintenanceInputMapper
from inframeld_backend.access.cli.mappers.recovery_maintenance_mapper import (
    RecoveryMaintenanceMapper,
)
from inframeld_backend.access.cli.mappers.stranded_authority_maintenance_mapper import (
    StrandedAuthorityMaintenanceMapper,
)


class MaintenanceCli:
    @staticmethod
    def read(
        source: BinaryIO,
    ) -> (
        ResumeIdentityRecoveryCleanupCommand
        | RepairStrandedAuthorityCommand
        | BootstrapFirstAdministratorCommand
    ):
        operation_id = None
        try:
            payload = source.read(65_537)
            values = MaintenanceInputMapper.read(payload)
            operation_id = MaintenanceInputMapper.correlation(values)
            if values.get("mode") == "resume-recovery-cleanup":
                return RecoveryMaintenanceMapper.read(payload)
            if values.get("mode") == "repair-stranded-authority":
                return StrandedAuthorityMaintenanceMapper.read(payload)
            if values.get("mode") == "bootstrap-first-administrator":
                return FirstAdministratorBootstrapMapper.read(payload)
            raise ValueError("Unsupported maintenance mode.")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise StrandedAuthorityMaintenanceInputError(operation_id) from None
