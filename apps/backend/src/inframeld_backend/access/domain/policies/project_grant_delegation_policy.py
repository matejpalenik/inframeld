from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.principal_access_policy import (
    PrincipalAccessPolicy,
)
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)


class ProjectGrantDelegationPolicy:
    """Decide delegation using facts for the same project and exact action."""

    @staticmethod
    def may_delegate_project_action(
        *,
        actor_access: PrincipalAccessPolicyInput,
        actor_is_project_member: bool,
        actor_can_grant_action: bool,
    ) -> bool:
        """Check the grantor before revealing anything about the recipient."""
        return (
            actor_access.principal.kind is PrincipalKind.HUMAN
            and PrincipalAccessPolicy.may_use_product(actor_access)
            and actor_is_project_member
            and actor_can_grant_action
        )

    @staticmethod
    def may_assign_use_only_to_human(
        *,
        actor_access: PrincipalAccessPolicyInput,
        recipient: Principal,
        actor_is_project_member: bool,
        recipient_is_project_member: bool,
        actor_can_grant_action: bool,
    ) -> bool:
        return (
            ProjectGrantDelegationPolicy.may_delegate_project_action(
                actor_access=actor_access,
                actor_is_project_member=actor_is_project_member,
                actor_can_grant_action=actor_can_grant_action,
            )
            and recipient.kind is PrincipalKind.HUMAN
            and recipient.status is PrincipalStatus.ACTIVE
            and recipient.organization_id == actor_access.principal.organization_id
            and recipient_is_project_member
        )
