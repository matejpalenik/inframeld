from enum import StrEnum


class RecoveryMaintenanceErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    INSTALLATION_MISMATCH = "installation_mismatch"
    KEY_REUSED = "idempotency_key_reused"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    UNEXPECTED_ERROR = "unexpected_error"
    RUN_ACTIVE = "cleanup_run_active"
    EVIDENCE_MISSING = "recovery_evidence_missing"
    NOT_FOUND = "recovery_not_found"
