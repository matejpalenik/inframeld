from inframeld_backend.access.application.enums.recovery_maintenance_error_code import (
    RecoveryMaintenanceErrorCode,
)


class RecoveryMaintenanceError(Exception):
    """Expose a safe maintenance outcome without input or provider details."""

    def __init__(self, code: RecoveryMaintenanceErrorCode) -> None:
        super().__init__(code.value)
        self.code = code
