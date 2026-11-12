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


@pytest.mark.parametrize(
    "method,status,expected",
    [
        ("suspend", PrincipalStatus.ACTIVE, PrincipalStatus.SUSPENDED),
        ("suspend", PrincipalStatus.SUSPENDED, PrincipalStatus.SUSPENDED),
        ("restore", PrincipalStatus.SUSPENDED, PrincipalStatus.ACTIVE),
        ("restore", PrincipalStatus.ACTIVE, PrincipalStatus.ACTIVE),
    ],
)
def test_deliberate_human_transition_preserves_identity_and_the_original_snapshot(
    method: str, status: PrincipalStatus, expected: PrincipalStatus
) -> None:
    principal = Principal(
        PrincipalId(uuid4()), OrganizationId(uuid4()), PrincipalKind.HUMAN, status
    )
    changed = getattr(principal, method)()
    assert changed.id == principal.id and changed.organization_id == principal.organization_id
    assert changed.status is expected and principal.status is status


@pytest.mark.parametrize("method", ["suspend", "restore"])
@pytest.mark.parametrize(
    "kind,status",
    [
        (PrincipalKind.HUMAN, PrincipalStatus.RETIRED),
        (PrincipalKind.APPLICATION, PrincipalStatus.ACTIVE),
    ],
)
def test_human_lifecycle_cannot_revive_retirement_or_act_on_applications(
    method: str, kind: PrincipalKind, status: PrincipalStatus
) -> None:
    from inframeld_backend.shared.domain.errors.domain_errors import InvalidStateTransitionError

    principal = Principal(PrincipalId(uuid4()), OrganizationId(uuid4()), kind, status)
    with pytest.raises(InvalidStateTransitionError):
        getattr(principal, method)()
