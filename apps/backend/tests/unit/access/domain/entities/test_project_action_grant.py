from dataclasses import FrozenInstanceError, replace
from uuid import UUID

import pytest

from inframeld_backend.access.domain.entities.project_action_grant import ProjectActionGrant
from inframeld_backend.access.domain.enums.project_grant_level import ProjectGrantLevel
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId

PROJECT = ProjectId(UUID(int=1))
RECIPIENT = PrincipalId(UUID(int=2))
ACTOR = PrincipalId(UUID(int=3))
ACTION = ActionId("create-access-groups")


def test_factory_creates_an_attributed_use_only_assignment() -> None:
    """The factory chooses the permission level instead of accepting delegation rights."""
    grant = ProjectActionGrant.create_use_only(
        project_id=PROJECT,
        recipient_principal_id=RECIPIENT,
        action_id=ACTION,
        assigned_by_principal_id=ACTOR,
    )
    assert grant.project_id == PROJECT
    assert grant.recipient_principal_id == RECIPIENT
    assert grant.action_id == ACTION
    assert grant.level is ProjectGrantLevel.USE_ONLY
    assert grant.assigned_by_principal_id == ACTOR


def test_identity_survives_level_and_attribution_changes() -> None:
    original = ProjectActionGrant(PROJECT, RECIPIENT, ACTION, ProjectGrantLevel.USE_ONLY, None)
    changed = replace(
        original, level=ProjectGrantLevel.USE_AND_GRANT, assigned_by_principal_id=ACTOR
    )
    assert original == changed
    assert hash(original) == hash(changed)
    assert original.assigned_by_principal_id is None


@pytest.mark.parametrize(
    "grant",
    [
        ProjectActionGrant(
            ProjectId(UUID(int=4)), RECIPIENT, ACTION, ProjectGrantLevel.USE_ONLY, None
        ),
        ProjectActionGrant(PROJECT, ACTOR, ACTION, ProjectGrantLevel.USE_ONLY, None),
        ProjectActionGrant(
            PROJECT, RECIPIENT, ActionId("create-pipelines"), ProjectGrantLevel.USE_ONLY, None
        ),
    ],
)
def test_another_target_recipient_or_action_has_different_identity(
    grant: ProjectActionGrant,
) -> None:
    assert grant != ProjectActionGrant(PROJECT, RECIPIENT, ACTION, ProjectGrantLevel.USE_ONLY, None)


def test_child_state_cannot_bypass_aggregate_mutations() -> None:
    grant = ProjectActionGrant(PROJECT, RECIPIENT, ACTION, ProjectGrantLevel.USE_ONLY, None)
    with pytest.raises(FrozenInstanceError):
        grant.__setattr__("level", ProjectGrantLevel.USE_AND_GRANT)
