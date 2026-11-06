"""Check membership and management remain distinct through removal and rejoining."""

import pytest

from inframeld_backend.access.domain.policies.access_group_relationship_policy import (
    AccessGroupRelationshipPolicy,
)
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)


@pytest.mark.parametrize(
    "before",
    [
        AccessGroupRelationships(False, False),
        AccessGroupRelationships(True, False),
        AccessGroupRelationships(True, True),
    ],
)
def test_appointment_always_includes_ordinary_membership(before: AccessGroupRelationships) -> None:
    assert AccessGroupRelationshipPolicy.appoint_manager(before) == AccessGroupRelationships(
        True, True
    )


def test_demotion_retains_ordinary_membership() -> None:
    assert AccessGroupRelationshipPolicy.remove_manager(
        AccessGroupRelationships(True, True)
    ) == AccessGroupRelationships(True, False)


def test_member_removal_and_rejoin_restore_no_management() -> None:
    removed = AccessGroupRelationshipPolicy.remove_member(AccessGroupRelationships(True, True))
    assert removed == AccessGroupRelationships(False, False)
    assert AccessGroupRelationshipPolicy.add_member(removed) == AccessGroupRelationships(
        True, False
    )


def test_adding_an_existing_manager_preserves_management() -> None:
    before = AccessGroupRelationships(True, True)
    assert AccessGroupRelationshipPolicy.add_member(before) == before
