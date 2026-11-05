from uuid import UUID

import pytest

from inframeld_backend.access.domain.entities.project_membership import ProjectMembership
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_grant_level import ProjectGrantLevel
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId

ACTOR = PrincipalId(UUID(int=1))
OTHER = PrincipalId(UUID(int=9))
ACTION = ActionId("inspect-budget")


def _membership(kind: PrincipalKind = PrincipalKind.HUMAN) -> ProjectMembership:
    return ProjectMembership(
        organization_id=OrganizationId(UUID(int=2)),
        project_id=ProjectId(UUID(int=3)),
        principal_id=PrincipalId(UUID(int=4)),
        principal_kind=kind,
        grants=(),
    )


def test_set_changes_level_without_replacing_original_assignment_attribution() -> None:
    member = _membership()
    assert member.set_action_grant(
        action_id=ACTION, level=ProjectGrantLevel.USE_ONLY, assigned_by_principal_id=ACTOR
    )
    first = member.grants[0]
    assert member.set_action_grant(
        action_id=ACTION, level=ProjectGrantLevel.USE_AND_GRANT, assigned_by_principal_id=OTHER
    )
    assert member.grants[0].identity == first.identity
    assert member.grants[0].level is ProjectGrantLevel.USE_AND_GRANT
    assert member.grants[0].assigned_by_principal_id == ACTOR


def test_equal_level_is_a_noop_and_preserves_the_existing_child() -> None:
    member = _membership()
    member.assign_use_only_grant(action_id=ACTION, assigned_by_principal_id=ACTOR)
    first = member.grants[0]
    assert not member.set_action_grant(
        action_id=ACTION, level=ProjectGrantLevel.USE_ONLY, assigned_by_principal_id=OTHER
    )
    assert member.grants[0] is first


def test_remove_then_reassign_creates_new_attribution_and_preserves_other_actions() -> None:
    member = _membership()
    member.assign_use_only_grant(action_id=ACTION, assigned_by_principal_id=ACTOR)
    other_action = ActionId("inspect-feedback")
    member.assign_use_only_grant(action_id=other_action, assigned_by_principal_id=ACTOR)
    assert member.remove_action_grant(action_id=ACTION)
    assert not member.remove_action_grant(action_id=ACTION)
    assert [x.action_id for x in member.grants] == [other_action]
    assert member.set_action_grant(
        action_id=ACTION, level=ProjectGrantLevel.USE_ONLY, assigned_by_principal_id=OTHER
    )
    assert member.grants[-1].assigned_by_principal_id == OTHER


@pytest.mark.parametrize(
    ("kind", "action", "level"),
    [
        (PrincipalKind.APPLICATION, ACTION, ProjectGrantLevel.USE_AND_GRANT),
        (PrincipalKind.APPLICATION, ActionId("manage-budget"), ProjectGrantLevel.USE_ONLY),
        (PrincipalKind.HUMAN, ActionId("query"), ProjectGrantLevel.USE_ONLY),
    ],
)
def test_unsupported_assignment_cannot_mutate_a_membership(
    kind: PrincipalKind, action: ActionId, level: ProjectGrantLevel
) -> None:
    member = _membership(kind)
    with pytest.raises(ValueError):
        member.set_action_grant(action_id=action, level=level, assigned_by_principal_id=ACTOR)
    assert member.grants == ()


def test_application_can_receive_the_two_eligible_project_use_actions() -> None:
    member = _membership(PrincipalKind.APPLICATION)
    for action in (ACTION, ActionId("inspect-feedback")):
        assert member.set_action_grant(
            action_id=action, level=ProjectGrantLevel.USE_ONLY, assigned_by_principal_id=ACTOR
        )
    assert len(member.grants) == 2
