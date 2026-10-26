from enum import StrEnum


class IdentityRecoveryEvidenceType(StrEnum):
    RECOVERY_CODE_VERIFIED = "recovery-code-verified"
    SETTINGS_FLOW_ASSOCIATED = "settings-flow-associated"
    PASSWORD_SETTINGS_SAVED = "password-settings-saved"
