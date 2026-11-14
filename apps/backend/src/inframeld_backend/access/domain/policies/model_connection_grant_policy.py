from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)


class ModelConnectionGrantPolicy:
    """Keep model delegation human-only and applications limited to exact view/use."""

    @staticmethod
    def supports_recipient(action: ModelConnectionAction, kind: PrincipalKind) -> bool:
        return kind is PrincipalKind.HUMAN or (
            kind is PrincipalKind.APPLICATION
            and action in {ModelConnectionAction.VIEW_CONFIGURATION, ModelConnectionAction.USE}
        )

    @staticmethod
    def may_assign(
        *,
        recipient_access: PrincipalAccessPolicyInput,
        is_project_member: bool,
        has_coherent_identity: bool,
        application_is_project_bound: bool,
        can_grant: bool,
    ) -> bool:
        return (
            PrincipalAccessPolicy.may_use_product(recipient_access)
            and is_project_member
            and (
                has_coherent_identity
                if recipient_access.principal.kind is PrincipalKind.HUMAN
                else application_is_project_bound and not can_grant
            )
        )
