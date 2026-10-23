from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)


class PrincipalAccessPolicy:
    """Decide current account activity and common product eligibility."""

    @staticmethod
    def is_account_active(principal: Principal) -> bool:
        return principal.status is PrincipalStatus.ACTIVE

    @staticmethod
    def may_use_product(policy_input: PrincipalAccessPolicyInput) -> bool:
        return (
            PrincipalAccessPolicy.is_account_active(policy_input.principal)
            and not policy_input.has_pending_recovery
        )
