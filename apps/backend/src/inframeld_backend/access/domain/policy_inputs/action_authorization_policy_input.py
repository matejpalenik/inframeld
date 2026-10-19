from dataclasses import dataclass

from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)


@dataclass(frozen=True, slots=True)
class ActionAuthorizationPolicyInput:
    """Combine caller eligibility with authority for the exact project action."""

    principal_access: PrincipalAccessPolicyInput
    is_project_member: bool
    has_exact_action_grant: bool
