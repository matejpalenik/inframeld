from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.application.commands.resume_identity_recovery_cleanup_command import (
    ResumeIdentityRecoveryCleanupCommand,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_resume_result_dto import (
    IdentityRecoveryCleanupResumeResultDTO,
)
from inframeld_backend.access.application.enums.recovery_maintenance_mode import (
    RecoveryMaintenanceMode,
)


@dataclass(frozen=True, slots=True)
class IdentityRecoveryMaintenanceReceiptDTO:
    """Keep the accepted meaning and original result as one operator audit record."""

    command: ResumeIdentityRecoveryCleanupCommand
    authorized_at: datetime
    result: IdentityRecoveryCleanupResumeResultDTO

    mode: RecoveryMaintenanceMode = RecoveryMaintenanceMode.RESUME_RECOVERY_CLEANUP
