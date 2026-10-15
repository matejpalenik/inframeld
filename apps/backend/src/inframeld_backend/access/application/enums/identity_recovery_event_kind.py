from enum import StrEnum


class IdentityRecoveryEventKind(StrEnum):
    RECOVERY = "recovery"
    PASSWORD_RESET = "password-reset"
