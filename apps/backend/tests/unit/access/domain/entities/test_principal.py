"""Check that account-state snapshots preserve principal identity."""

from dataclasses import FrozenInstanceError, replace
from uuid import uuid4

import pytest

from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


def test_principal_identity_survives_status_changes() -> None:
    """Treat two snapshots of the same principal as the same domain entity."""
    principal = Principal(
        PrincipalId(uuid4()), OrganizationId(uuid4()), PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
    )
    suspended = replace(principal, status=PrincipalStatus.SUSPENDED)
    assert principal == suspended
    assert hash(principal) == hash(suspended)
    assert principal != replace(principal, id=PrincipalId(uuid4()))


def test_principal_state_is_immutable() -> None:
    """Prevent mutation of account state already returned from a read boundary."""
    principal = Principal(
        PrincipalId(uuid4()), OrganizationId(uuid4()), PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
    )
    with pytest.raises(FrozenInstanceError):
        principal.__setattr__("status", PrincipalStatus.SUSPENDED)
