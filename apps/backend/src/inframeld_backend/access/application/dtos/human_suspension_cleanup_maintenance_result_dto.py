from dataclasses import dataclass

from inframeld_backend.access.application.enums.human_suspension_cleanup_continue_outcome import (
    HumanSuspensionCleanupContinueOutcome,
)
from inframeld_backend.access.application.enums.human_suspension_cleanup_execution_state import (
    HumanSuspensionCleanupExecutionState,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class HumanSuspensionCleanupMaintenanceResultDTO:
    operation_id: OperationId
    installation_id: InstallationId
    cleanup_operation_id: OperationId
    outcome: HumanSuspensionCleanupContinueOutcome | HumanSuspensionCleanupExecutionState
    kratos_sessions: IdentityRecoveryCleanupState | None = None
    hydra_cli_grants: IdentityRecoveryCleanupState | None = None
    hydra_remembered_logins: IdentityRecoveryCleanupState | None = None
