"""Check membership and management remain distinct through removal and rejoining."""

from uuid import UUID

import pytest

from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.access_group_relationship_policy import (
    AccessGroupRelationshipPolicy,
)
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@pytest.mark.parametrize(
    "before",
    [
        AccessGroupRelationships(member=False, manager=False),
        AccessGroupRelationships(member=True, manager=False),
        AccessGroupRelationships(member=True, manager=True),
    ],
)
def test_appointment_always_includes_ordinary_membership(before: AccessGroupRelationships) -> None:
    assert AccessGroupRelationshipPolicy.appoint_manager(before) == AccessGroupRelationships(
        member=True, manager=True
    )


def test_demotion_retains_ordinary_membership() -> None:
    assert AccessGroupRelationshipPolicy.remove_manager(
        AccessGroupRelationships(member=True, manager=True)
    ) == AccessGroupRelationships(member=True, manager=False)


def test_member_removal_and_rejoin_restore_no_management() -> None:
    removed = AccessGroupRelationshipPolicy.remove_member(
        AccessGroupRelationships(member=True, manager=True)
    )
    assert removed == AccessGroupRelationships(member=False, manager=False)
    assert AccessGroupRelationshipPolicy.add_member(removed) == AccessGroupRelationships(
        member=True, manager=False
    )


def test_adding_an_existing_manager_preserves_management() -> None:
    before = AccessGroupRelationships(member=True, manager=True)
    assert AccessGroupRelationshipPolicy.add_member(before) == before


@pytest.mark.parametrize(
    "kind, is_project_member, has_coherent_identity, has_pending_recovery, status, expected",
    [
        (PrincipalKind.HUMAN, True, True, False, PrincipalStatus.ACTIVE, True),
        (PrincipalKind.APPLICATION, True, False, False, PrincipalStatus.ACTIVE, True),
        (PrincipalKind.HUMAN, False, True, False, PrincipalStatus.ACTIVE, False),
        (PrincipalKind.APPLICATION, False, False, False, PrincipalStatus.ACTIVE, False),
        (PrincipalKind.HUMAN, True, False, False, PrincipalStatus.ACTIVE, False),
        (PrincipalKind.HUMAN, True, True, True, PrincipalStatus.ACTIVE, False),
        (PrincipalKind.APPLICATION, True, False, True, PrincipalStatus.ACTIVE, False),
        (PrincipalKind.HUMAN, True, True, False, PrincipalStatus.SUSPENDED, False),
        (PrincipalKind.APPLICATION, True, False, False, PrincipalStatus.RETIRED, False),
    ],
)
def test_new_membership_requires_an_eligible_current_project_account(
    kind: PrincipalKind,
    is_project_member: bool,
    has_coherent_identity: bool,
    has_pending_recovery: bool,
    status: PrincipalStatus,
    expected: bool,
) -> None:
    principal = Principal(
        id=PrincipalId(UUID(int=1)),
        organization_id=OrganizationId(UUID(int=2)),
        kind=kind,
        status=status,
    )

    assert (
        AccessGroupRelationshipPolicy.may_add_member(
            principal=principal,
            is_project_member=is_project_member,
            has_coherent_identity=has_coherent_identity,
            has_pending_recovery=has_pending_recovery,
        )
        is expected
    )


@pytest.mark.parametrize(
    "principal_kind, expected", [(PrincipalKind.HUMAN, True), (PrincipalKind.APPLICATION, False)]
)
def test_only_humans_can_be_manager_targets(principal_kind: PrincipalKind, expected: bool) -> None:
    assert AccessGroupRelationshipPolicy.supports_manager_kind(principal_kind) is expected
