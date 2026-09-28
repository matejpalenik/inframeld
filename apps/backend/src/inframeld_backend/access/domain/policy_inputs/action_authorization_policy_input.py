from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActionAuthorizationPolicyInput:
    """Supply the current eligibility and exact grant needed to decide action admission."""

    principal_is_active: bool
    is_project_member: bool
    has_exact_action_grant: bool
