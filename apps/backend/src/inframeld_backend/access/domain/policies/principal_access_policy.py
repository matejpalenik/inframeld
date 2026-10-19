from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)


class PrincipalAccessPolicy:
    """Decide common product eligibility before operation-specific authority."""

    @staticmethod
    def may_use_product(policy_input: PrincipalAccessPolicyInput) -> bool:
        return (
            policy_input.principal.status is PrincipalStatus.ACTIVE
            and not policy_input.has_pending_recovery
        )
