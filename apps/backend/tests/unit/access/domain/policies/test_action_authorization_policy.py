from uuid import UUID

import pytest

from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.action_authorization_policy import (
    ActionAuthorizationPolicy,
)
from inframeld_backend.access.domain.policy_inputs.action_authorization_policy_input import (
    ActionAuthorizationPolicyInput,
)
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@pytest.mark.parametrize("kind", list(PrincipalKind))
@pytest.mark.parametrize(
    ("status", "pending_recovery", "member", "granted", "expected"),
    [
        pytest.param(
            PrincipalStatus.ACTIVE,
            False,
            True,
            True,
            True,
            id="eligible-member-with-grant",
        ),
        pytest.param(
            PrincipalStatus.ACTIVE,
            False,
            False,
            True,
            False,
            id="nonmember",
        ),
        pytest.param(
            PrincipalStatus.ACTIVE,
            False,
            True,
            False,
            False,
            id="missing-grant",
        ),
        pytest.param(
            PrincipalStatus.SUSPENDED,
            False,
            True,
            True,
            False,
            id="suspended",
        ),
        pytest.param(
            PrincipalStatus.RETIRED,
            False,
            True,
            True,
            False,
            id="retired",
        ),
        pytest.param(
            PrincipalStatus.ACTIVE,
            True,
            True,
            True,
            False,
            id="pending-recovery",
        ),
    ],
)
def test_action_requires_eligibility_membership_and_exact_grant(
    kind: PrincipalKind,
    status: PrincipalStatus,
    pending_recovery: bool,
    member: bool,
    granted: bool,
    expected: bool,
) -> None:
    """An existing grant cannot bypass account eligibility or project membership."""
    principal = Principal(
        id=PrincipalId(UUID(int=1)),
        organization_id=OrganizationId(UUID(int=2)),
        kind=kind,
        status=status,
    )
    policy_input = ActionAuthorizationPolicyInput(
        principal_access=PrincipalAccessPolicyInput(
            principal=principal,
            has_pending_recovery=pending_recovery,
        ),
        is_project_member=member,
        has_exact_action_grant=granted,
    )

    assert ActionAuthorizationPolicy.may_perform_action(policy_input) is expected
