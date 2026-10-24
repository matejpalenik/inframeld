from uuid import UUID

import pytest

from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.principal_access_policy import (
    PrincipalAccessPolicy,
)
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@pytest.mark.parametrize("kind", list(PrincipalKind))
@pytest.mark.parametrize(
    ("status", "has_pending_recovery", "expected"),
    [
        pytest.param(PrincipalStatus.ACTIVE, False, True, id="active-without-recovery"),
        pytest.param(PrincipalStatus.ACTIVE, True, False, id="active-with-recovery"),
        pytest.param(PrincipalStatus.SUSPENDED, False, False, id="suspended"),
        pytest.param(PrincipalStatus.SUSPENDED, True, False, id="suspended-with-recovery"),
        pytest.param(PrincipalStatus.RETIRED, False, False, id="retired"),
        pytest.param(PrincipalStatus.RETIRED, True, False, id="retired-with-recovery"),
    ],
)
def test_product_eligibility_respects_account_status_and_recovery(
    kind: PrincipalKind,
    status: PrincipalStatus,
    has_pending_recovery: bool,
    expected: bool,
) -> None:
    """Recovery blocks active accounts, while clearing recovery never lifts suspension."""
    principal = Principal(
        id=PrincipalId(UUID(int=1)),
        organization_id=OrganizationId(UUID(int=2)),
        kind=kind,
        status=status,
    )
    policy_input = PrincipalAccessPolicyInput(
        principal=principal, has_pending_recovery=has_pending_recovery, credential_is_current=True
    )

    assert PrincipalAccessPolicy.may_use_product(policy_input) is expected


@pytest.mark.parametrize("kind", list(PrincipalKind))
@pytest.mark.parametrize("status", list(PrincipalStatus))
def test_account_activity_is_available_separately_from_product_access(
    kind: PrincipalKind, status: PrincipalStatus
) -> None:
    """Recovery can check local account status without treating itself as a product grant."""
    principal = Principal(
        id=PrincipalId(UUID(int=1)),
        organization_id=OrganizationId(UUID(int=2)),
        kind=kind,
        status=status,
    )

    assert PrincipalAccessPolicy.is_account_active(principal) is (status is PrincipalStatus.ACTIVE)


def test_stale_credential_keeps_an_active_unblocked_account_ineligible() -> None:
    principal = Principal(
        id=PrincipalId(UUID(int=1)),
        organization_id=OrganizationId(UUID(int=2)),
        kind=PrincipalKind.HUMAN,
        status=PrincipalStatus.ACTIVE,
    )
    assert not PrincipalAccessPolicy.may_use_product(
        PrincipalAccessPolicyInput(principal, False, credential_is_current=False)
    )
