from enum import StrEnum


class HumanSuspensionCleanupMaintenanceErrorCode(StrEnum):
    INSTALLATION_MISMATCH = "installation_mismatch"
    KEY_REUSED = "idempotency_key_reused"
    NOT_FOUND = "suspension_cleanup_not_found"
    NOT_CONTINUABLE = "suspension_cleanup_not_continuable"
