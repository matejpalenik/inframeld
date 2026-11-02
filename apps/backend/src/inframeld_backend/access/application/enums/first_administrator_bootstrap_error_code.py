from enum import StrEnum


class FirstAdministratorBootstrapErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    INVALID_IDENTITY_PROOF = "invalid_identity_proof"
    IDENTITY_INELIGIBLE = "identity_ineligible"
    INSTALLATION_MISMATCH = "installation_mismatch"
    STALE_REVISION = "stale_revision"
    KEY_REUSED = "idempotency_key_reused"
    ALREADY_BOOTSTRAPPED = "already_bootstrapped"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    UNEXPECTED_ERROR = "unexpected_error"
