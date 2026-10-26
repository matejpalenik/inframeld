from enum import StrEnum


class IdentityRecoveryCleanupStep(StrEnum):
    CLI_GRANTS = "cli-grants"
    REMEMBERED_LOGINS = "remembered-logins"
