from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId


class HumanAdmissionPolicy:
    @staticmethod
    def may_authorize(
        eligibility: PrincipalAccessPolicyInput,
        *,
        has_admit_users: bool,
    ) -> bool:
        return (
            eligibility.principal.kind is PrincipalKind.HUMAN
            and PrincipalAccessPolicy.may_use_product(eligibility)
            and has_admit_users
        )

    @staticmethod
    def may_admit(
        *,
        principal: Principal | None,
        organization_id: OrganizationId,
        has_pending_recovery: bool,
    ) -> bool:
        return not has_pending_recovery and (
            principal is None
            or (
                principal.organization_id == organization_id
                and principal.kind is PrincipalKind.HUMAN
                and PrincipalAccessPolicy.is_account_active(principal)
            )
        )
