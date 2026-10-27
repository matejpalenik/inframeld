from dataclasses import replace
from uuid import UUID

import pytest

from inframeld_backend.access.domain.entities.project_action_grant import ProjectActionGrant
from inframeld_backend.access.domain.entities.project_membership import ProjectMembership
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_grant_level import ProjectGrantLevel
from inframeld_backend.access.domain.errors.project_grant_errors import (
    ProjectGrantAlreadyExistsError,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId

ORGANIZATION = OrganizationId(UUID(int=1))
PROJECT = ProjectId(UUID(int=2))
RECIPIENT = PrincipalId(UUID(int=3))
ACTOR = PrincipalId(UUID(int=4))
ACTION = ActionId("create-access-groups")
EXISTING = ProjectActionGrant(PROJECT, RECIPIENT, ACTION, ProjectGrantLevel.USE_ONLY, None)


def membership(
    *, grants: tuple[ProjectActionGrant, ...] = (), kind: PrincipalKind = PrincipalKind.HUMAN
) -> ProjectMembership:
    return ProjectMembership(
        organization_id=ORGANIZATION,
        project_id=PROJECT,
        principal_id=RECIPIENT,
        principal_kind=kind,
        grants=grants,
    )


def test_assignment_preserves_existing_state_and_adds_a_use_only_child() -> None:
    """Only this member's missing action is added, without replacing existing grants."""
    member = membership(grants=(EXISTING,))
    old_view = member.grants
    added = ActionId("create-pipelines")
    member.assign_use_only_grant(action_id=added, assigned_by_principal_id=ACTOR)
    assert member.organization_id == ORGANIZATION
    assert member.project_id == PROJECT
    assert member.principal_id == RECIPIENT
    assert member.principal_kind is PrincipalKind.HUMAN
    assert old_view == (EXISTING,)
    assert member.grants[0] is EXISTING
    assert len(member.grants) == 2
    new_grant = member.grants[1]
    assert new_grant.project_id == PROJECT
    assert new_grant.recipient_principal_id == RECIPIENT
    assert new_grant.action_id == added
    assert new_grant.level is ProjectGrantLevel.USE_ONLY
    assert new_grant.assigned_by_principal_id == ACTOR


@pytest.mark.parametrize("level", list(ProjectGrantLevel))
def test_existing_assignment_cannot_be_replaced_or_downgraded(level: ProjectGrantLevel) -> None:
    original = replace(EXISTING, level=level)
    member = membership(grants=(original,))
    with pytest.raises(ProjectGrantAlreadyExistsError):
        member.assign_use_only_grant(action_id=ACTION, assigned_by_principal_id=ACTOR)
    assert member.grants == (original,)
    assert member.grants[0] is original
    assert member.grants[0].level is level
    assert member.grants[0].assigned_by_principal_id is None


def test_second_assignment_in_the_same_aggregate_is_also_rejected() -> None:
    member = membership()
    member.assign_use_only_grant(action_id=ACTION, assigned_by_principal_id=ACTOR)
    with pytest.raises(ProjectGrantAlreadyExistsError):
        member.assign_use_only_grant(action_id=ACTION, assigned_by_principal_id=ACTOR)
    assert len(member.grants) == 1


@pytest.mark.parametrize(
    "grant",
    [
        replace(EXISTING, project_id=ProjectId(UUID(int=9))),
        replace(EXISTING, recipient_principal_id=ACTOR),
    ],
)
def test_reconstitution_rejects_grants_from_another_membership(grant: ProjectActionGrant) -> None:
    with pytest.raises(ValueError, match="another project membership"):
        membership(grants=(grant,))


def test_reconstitution_rejects_duplicate_actions() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        membership(grants=(EXISTING, replace(EXISTING, level=ProjectGrantLevel.USE_AND_GRANT)))


def test_application_cannot_be_reconstituted_with_delegation_rights() -> None:
    with pytest.raises(ValueError, match="delegation"):
        membership(
            kind=PrincipalKind.APPLICATION,
            grants=(replace(EXISTING, level=ProjectGrantLevel.USE_AND_GRANT),),
        )


def test_application_use_only_state_and_historical_null_attribution_are_valid() -> None:
    member = membership(kind=PrincipalKind.APPLICATION, grants=(EXISTING,))
    assert member.grants[0].level is ProjectGrantLevel.USE_ONLY
    assert member.grants[0].assigned_by_principal_id is None


def test_identity_uses_project_and_principal_instead_of_grant_state() -> None:
    empty = membership()
    populated = membership(grants=(EXISTING,))
    assert empty == populated
    assert hash(empty) == hash(populated)
    assert empty != ProjectMembership(
        organization_id=ORGANIZATION,
        project_id=ProjectId(UUID(int=9)),
        principal_id=RECIPIENT,
        principal_kind=PrincipalKind.HUMAN,
        grants=(),
    )
    assert empty != ProjectMembership(
        organization_id=ORGANIZATION,
        project_id=PROJECT,
        principal_id=ACTOR,
        principal_kind=PrincipalKind.HUMAN,
        grants=(),
    )


@pytest.mark.parametrize(
    "attribute", ["organization_id", "project_id", "principal_id", "principal_kind"]
)
def test_membership_identity_and_kind_are_read_only(attribute: str) -> None:
    member = membership()
    with pytest.raises(AttributeError):
        member.__setattr__(attribute, None)
