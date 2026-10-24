from dataclasses import dataclass

from inframeld_backend.access.domain.entities.principal import Principal


@dataclass(frozen=True, slots=True)
class PrincipalAccessPolicyInput:
    """Current eligibility for one attempt, including the human OAuth version check.

    Credential currentness is explicitly true when that version check does not apply.
    This input does not verify browser sessions or application keys.
    """

    principal: Principal
    has_pending_recovery: bool
    credential_is_current: bool
