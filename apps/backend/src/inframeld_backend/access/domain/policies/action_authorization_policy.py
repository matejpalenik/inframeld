from inframeld_backend.access.domain.policies.principal_access_policy import (
    PrincipalAccessPolicy,
)
from inframeld_backend.access.domain.policy_inputs.action_authorization_policy_input import (
    ActionAuthorizationPolicyInput,
)


class ActionAuthorizationPolicy:
    """Require an eligible project member with the exact action grant."""

    @staticmethod
    def may_perform_action(policy_input: ActionAuthorizationPolicyInput) -> bool:
        return (
            PrincipalAccessPolicy.may_use_product(policy_input.principal_access)
            and policy_input.is_project_member
            and policy_input.has_exact_action_grant
        )
