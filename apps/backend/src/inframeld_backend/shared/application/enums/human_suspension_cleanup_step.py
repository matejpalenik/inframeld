from enum import StrEnum


class HumanSuspensionCleanupStep(StrEnum):
    """Identify one independent outcome on the original suspension obligation."""

    KRATOS_SESSIONS = "kratos_sessions"
    HYDRA_CLI_GRANTS = "hydra_cli_grants"
    HYDRA_REMEMBERED_LOGINS = "hydra_remembered_logins"
