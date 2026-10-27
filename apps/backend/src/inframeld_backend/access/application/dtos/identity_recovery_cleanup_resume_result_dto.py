from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from inframeld_backend.access.application.enums.identity_recovery_cleanup_resume_outcome import (
    IdentityRecoveryCleanupResumeOutcome,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class IdentityRecoveryCleanupResumeResultDTO:
    operation_id: OperationId
    installation_id: InstallationId
    recovery_operation_id: OperationId
    outcome: IdentityRecoveryCleanupResumeOutcome
    released: bool
    run_id: UUID | None = None
    deadline: datetime | None = None
