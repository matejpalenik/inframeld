from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policy_inputs.organization_grant_candidate_policy_input import (
    OrganizationGrantCandidatePolicyInput,
)
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId


class OrganizationGrantPolicy:
    """Keep Organization delegation with eligible admitted humans and safe handover."""

    @staticmethod
    def supports_action(action_id: ActionId) -> bool:
        return action_id.value in frozenset(OrganizationAction)

    @staticmethod
    def may_manage(*, actor_access: PrincipalAccessPolicyInput, can_grant_action: bool) -> bool:
        return (
            actor_access.principal.kind is PrincipalKind.HUMAN
            and PrincipalAccessPolicy.may_use_product(actor_access)
            and can_grant_action
        )

    @staticmethod
    def may_receive(
        *, recipient_access: PrincipalAccessPolicyInput, has_coherent_identity: bool
    ) -> bool:
        return (
            recipient_access.principal.kind is PrincipalKind.HUMAN
            and has_coherent_identity
            and PrincipalAccessPolicy.may_use_product(recipient_access)
        )

    @staticmethod
    def has_remaining_grantor(
        candidates: tuple[OrganizationGrantCandidatePolicyInput, ...],
    ) -> bool:
        return any(
            candidate.can_grant
            and OrganizationGrantPolicy.may_receive(
                recipient_access=PrincipalAccessPolicyInput(
                    principal=candidate.principal,
                    has_pending_recovery=candidate.has_pending_recovery,
                    credential_is_current=True,
                ),
                has_coherent_identity=candidate.has_coherent_identity,
            )
            for candidate in candidates
        )
