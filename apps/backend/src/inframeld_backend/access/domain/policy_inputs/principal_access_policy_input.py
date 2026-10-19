from dataclasses import dataclass

from inframeld_backend.access.domain.entities.principal import Principal


@dataclass(frozen=True, slots=True)
class PrincipalAccessPolicyInput:
    """Account state and recovery restrictions observed for one access attempt."""

    principal: Principal
    has_pending_recovery: bool
