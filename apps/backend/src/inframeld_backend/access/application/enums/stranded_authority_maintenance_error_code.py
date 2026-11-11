from enum import StrEnum


class StrandedAuthorityMaintenanceErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    INVALID_IDENTITY_PROOF = "invalid_identity_proof"
    IDENTITY_INELIGIBLE = "identity_ineligible"
    INSTALLATION_MISMATCH = "installation_mismatch"
    STALE_REVISION = "stale_revision"
    REVISION_EXHAUSTED = "revision_exhausted"
    KEY_REUSED = "idempotency_key_reused"
    NOT_STRANDED = "responsibility_not_stranded"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    UNEXPECTED_ERROR = "unexpected_error"
