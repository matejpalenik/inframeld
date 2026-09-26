from inframeld_backend.access.domain.policy_inputs.action_authorization_policy_input import (
    ActionAuthorizationPolicyInput,
)


class ActionAuthorizationPolicy:
    """Require an active project member with the exact action grant."""

    @staticmethod
    def may_perform_action(policy_input: ActionAuthorizationPolicyInput) -> bool:
        return (
            policy_input.principal_is_active
            and policy_input.is_project_member
            and policy_input.has_exact_action_grant
        )
