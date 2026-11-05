from enum import StrEnum


class HydraCleanupOperation(StrEnum):
    """Select the provider cleanup endpoint without changing the subject scope."""

    CLI_GRANTS = "cli_grants"
    REMEMBERED_LOGINS = "remembered_logins"
