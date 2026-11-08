from datetime import datetime

from inframeld_backend.access.domain.policies.human_admission_policy import HumanAdmissionPolicy
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


class InvitationPolicy:
    @staticmethod
    def may_revoke(
        eligibility: PrincipalAccessPolicyInput,
        *,
        organization_id: OrganizationId,
        issuer_principal_id: PrincipalId,
        has_admit_users: bool,
        can_grant_admit_users: bool,
    ) -> bool:
        """Allow the current issuer or an eligible admission delegator in this Organization."""
        return (
            eligibility.principal.organization_id == organization_id
            and HumanAdmissionPolicy.may_authorize(eligibility, has_admit_users=has_admit_users)
            and (eligibility.principal.id == issuer_principal_id or can_grant_admit_users)
        )

    @staticmethod
    def may_consume(
        *,
        expires_at: datetime,
        current_time: datetime,
        revoked_at: datetime | None,
        consumed_at: datetime | None,
    ) -> bool:
        """Check only fresh token state, never eligibility or completed-replay authority.

        The application must look for a permitted retained original before using
        this predicate. An old completed activation does not become fresh again.
        """
        return expires_at > current_time and revoked_at is None and consumed_at is None
