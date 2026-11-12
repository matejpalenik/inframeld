from inframeld_backend.access.application.enums.human_suspension_cleanup_maintenance_error_code import (
    HumanSuspensionCleanupMaintenanceErrorCode,
)


class HumanSuspensionCleanupMaintenanceError(Exception):
    """Return a safe host outcome without exposing the target or storage detail."""

    def __init__(self, code: HumanSuspensionCleanupMaintenanceErrorCode) -> None:
        super().__init__(code.value)
        self.code = code
