from inframeld_backend.access.domain.enums.application_account_action import (
    ApplicationAccountAction,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId


class ApplicationAccountGrantPolicy:
    """Reserve administration of one application account for eligible human members."""

    @staticmethod
    def supports_recipient(*, action_id: ActionId, kind: PrincipalKind) -> bool:
        return kind is PrincipalKind.HUMAN and action_id.value in frozenset(
            ApplicationAccountAction
        )

    @staticmethod
    def may_receive(
        *,
        recipient_access: PrincipalAccessPolicyInput,
        is_project_member: bool,
        has_coherent_identity: bool,
    ) -> bool:
        return (
            recipient_access.principal.kind is PrincipalKind.HUMAN
            and is_project_member
            and has_coherent_identity
            and PrincipalAccessPolicy.may_use_product(recipient_access)
        )
