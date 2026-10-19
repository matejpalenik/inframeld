"""Require current local human eligibility after external verification."""

from uuid import uuid4

import pytest

from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.human_authentication_policy import (
    HumanAuthenticationPolicy,
)
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@pytest.mark.parametrize("kind", list(PrincipalKind))
@pytest.mark.parametrize("status", list(PrincipalStatus))
@pytest.mark.parametrize("has_pending_recovery", [False, True])
def test_only_eligible_humans_without_recovery_blocks_may_authenticate(
    kind: PrincipalKind,
    status: PrincipalStatus,
    has_pending_recovery: bool,
) -> None:
    """Provider approval cannot bypass account state or an unreleased recovery block."""
    principal = Principal(
        id=PrincipalId(uuid4()),
        organization_id=OrganizationId(uuid4()),
        kind=kind,
        status=status,
    )
    policy_input = PrincipalAccessPolicyInput(
        principal=principal,
        has_pending_recovery=has_pending_recovery,
    )

    assert HumanAuthenticationPolicy.may_authenticate(policy_input) is (
        kind is PrincipalKind.HUMAN
        and status is PrincipalStatus.ACTIVE
        and not has_pending_recovery
    )
