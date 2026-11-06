from inframeld_backend.access.domain.enums.access_group_action import AccessGroupAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId


class AccessGroupGrantPolicy:
    """Keep exact document delegation distinct from ordinary group management."""

    @staticmethod
    def supports_recipient(*, action_id: ActionId, kind: PrincipalKind, can_grant: bool) -> bool:
        return action_id.value in frozenset(AccessGroupAction) and (
            kind is PrincipalKind.HUMAN or (kind is PrincipalKind.APPLICATION and not can_grant)
        )

    @staticmethod
    def may_manage(
        *,
        actor_access: PrincipalAccessPolicyInput,
        is_project_member: bool,
        can_grant_action: bool,
        is_group_member: bool,
        is_group_manager: bool,
    ) -> bool:
        return (
            actor_access.principal.kind is PrincipalKind.HUMAN
            and is_project_member
            and PrincipalAccessPolicy.may_use_product(actor_access)
            and (can_grant_action or (is_group_member and is_group_manager))
        )

    @staticmethod
    def may_receive(
        *,
        recipient_access: PrincipalAccessPolicyInput,
        is_project_member: bool,
        has_coherent_identity: bool,
        application_is_bound: bool,
    ) -> bool:
        return (
            is_project_member
            and PrincipalAccessPolicy.may_use_product(recipient_access)
            and (
                has_coherent_identity
                if recipient_access.principal.kind is PrincipalKind.HUMAN
                else application_is_bound
            )
        )
