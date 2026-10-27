from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.principal_access_policy import (
    PrincipalAccessPolicy,
)
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)


class HumanAuthenticationPolicy:
    """Require a human who passes the shared product-eligibility rule."""

    @staticmethod
    def may_authenticate(policy_input: PrincipalAccessPolicyInput) -> bool:
        return (
            policy_input.principal.kind is PrincipalKind.HUMAN
            and PrincipalAccessPolicy.may_use_product(policy_input)
        )
