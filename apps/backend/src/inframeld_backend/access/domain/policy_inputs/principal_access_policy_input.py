from dataclasses import dataclass

from inframeld_backend.access.domain.entities.principal import Principal


@dataclass(frozen=True, slots=True)
class PrincipalAccessPolicyInput:
    """Current eligibility for one attempt, including current credential observations.

    Credential currentness follows the presented evidence family and fresh stored facts.
    This input does not verify browser sessions or application keys.
    """

    principal: Principal
    has_pending_recovery: bool
    credential_is_current: bool
