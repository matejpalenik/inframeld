"""Verify nominal identifier validation and the local human admission policy."""

from dataclasses import FrozenInstanceError, replace
from typing import cast
from uuid import UUID, uuid4

import pytest

from inframeld_backend.access.domain.group_values import AccessGroupId
from inframeld_backend.access.domain.human_authentication_policy import may_authenticate_human
from inframeld_backend.access.domain.organization_values import OrganizationId
from inframeld_backend.access.domain.principal import (
    Principal,
    PrincipalId,
    PrincipalKind,
    PrincipalStatus,
)
from inframeld_backend.access.domain.project_values import ProjectId


@pytest.mark.parametrize("identifier_type", [PrincipalId, OrganizationId, ProjectId, AccessGroupId])
def test_identifier_requires_a_parsed_uuid(
    identifier_type: type[PrincipalId]
    | type[OrganizationId]
    | type[ProjectId]
    | type[AccessGroupId],
) -> None:
    """Reject raw external input even when it bypasses static checking."""
    with pytest.raises(TypeError, match="UUID"):
        identifier_type(cast(UUID, "not-parsed"))


def test_identifiers_are_immutable_and_distinguish_entity_kinds() -> None:
    """Keep equal UUIDs for different entity kinds distinct in sets and comparisons."""
    value = uuid4()
    principal_id = PrincipalId(value)
    assert principal_id == PrincipalId(value)
    assert len({principal_id, ProjectId(value), OrganizationId(value)}) == 3
    with pytest.raises(FrozenInstanceError):
        principal_id.__setattr__("value", uuid4())


def test_principal_identity_survives_status_changes() -> None:
    """Treat two snapshots of the same principal as the same domain entity."""
    principal = Principal(
        PrincipalId(uuid4()), OrganizationId(uuid4()), PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
    )
    suspended = replace(principal, status=PrincipalStatus.SUSPENDED)
    assert principal == suspended
    assert hash(principal) == hash(suspended)
    assert principal != replace(principal, id=PrincipalId(uuid4()))


@pytest.mark.parametrize("kind", list(PrincipalKind))
@pytest.mark.parametrize("status", list(PrincipalStatus))
def test_only_active_humans_may_authenticate(kind: PrincipalKind, status: PrincipalStatus) -> None:
    """Require human kind and active status independently of provider verification."""
    principal = Principal(PrincipalId(uuid4()), OrganizationId(uuid4()), kind, status)
    assert may_authenticate_human(principal) is (
        kind is PrincipalKind.HUMAN and status is PrincipalStatus.ACTIVE
    )


@pytest.mark.parametrize("value", [UUID(int=0), UUID("550e8400-e29b-11d4-a716-446655440000")])
def test_identifiers_preserve_existing_uuid_values(value: UUID) -> None:
    """Accept zero and non-v4 UUIDs without adding an unrequested identity restriction."""
    assert PrincipalId(value).value == value
    assert OrganizationId(value).value == value
    assert ProjectId(value).value == value
    assert AccessGroupId(value).value == value


def test_principal_state_is_immutable() -> None:
    """Prevent mutation of account state already returned from a read boundary."""
    principal = Principal(
        PrincipalId(uuid4()), OrganizationId(uuid4()), PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
    )
    with pytest.raises(FrozenInstanceError):
        principal.__setattr__("status", PrincipalStatus.SUSPENDED)
