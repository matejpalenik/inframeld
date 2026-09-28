"""Require current local human eligibility after external verification."""

from uuid import uuid4

import pytest

from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.human_authentication_policy import (
    HumanAuthenticationPolicy,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@pytest.mark.parametrize("kind", list(PrincipalKind))
@pytest.mark.parametrize("status", list(PrincipalStatus))
def test_only_active_humans_may_authenticate(kind: PrincipalKind, status: PrincipalStatus) -> None:
    """Require human kind and active status independently of provider verification."""
    principal = Principal(PrincipalId(uuid4()), OrganizationId(uuid4()), kind, status)
    assert HumanAuthenticationPolicy.may_authenticate(principal) is (
        kind is PrincipalKind.HUMAN and status is PrincipalStatus.ACTIVE
    )
