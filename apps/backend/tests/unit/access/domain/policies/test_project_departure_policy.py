from dataclasses import replace
from uuid import UUID

import pytest

from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.project_departure_policy import ProjectDeparturePolicy
from inframeld_backend.access.domain.policy_inputs.project_departure_candidate_policy_input import (
    ProjectDepartureCandidatePolicyInput,
)
from inframeld_backend.access.domain.policy_inputs.project_departure_responsibility_policy_input import (
    ProjectDepartureResponsibilityPolicyInput,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId

HUMAN = Principal(
    PrincipalId(UUID(int=2)),
    OrganizationId(UUID(int=1)),
    PrincipalKind.HUMAN,
    PrincipalStatus.ACTIVE,
)
CANDIDATE = ProjectDepartureCandidatePolicyInput(HUMAN, False, True, True, True, False, False)


def test_each_exact_responsibility_needs_a_remaining_eligible_human() -> None:
    supported = ProjectDepartureResponsibilityPolicyInput(False, False, (CANDIDATE,))
    assert ProjectDeparturePolicy.may_depart((supported,))
    assert not ProjectDeparturePolicy.may_depart((supported, replace(supported, candidates=())))
    assert ProjectDeparturePolicy.may_depart(())


@pytest.mark.parametrize(
    "field", ["has_pending_recovery", "is_project_member", "has_coherent_identity"]
)
def test_ineligible_or_incoherent_relationship_cannot_keep_authority(field: str) -> None:
    candidate = replace(CANDIDATE, **{field: field == "has_pending_recovery"})
    assert not ProjectDeparturePolicy.may_depart(
        (ProjectDepartureResponsibilityPolicyInput(False, False, (candidate,)),)
    )


@pytest.mark.parametrize("kind", [PrincipalKind.APPLICATION])
def test_application_cannot_replace_a_human_grantor(kind: PrincipalKind) -> None:
    candidate = replace(CANDIDATE, principal=replace(HUMAN, kind=kind))
    assert not ProjectDeparturePolicy.may_depart(
        (ProjectDepartureResponsibilityPolicyInput(False, False, (candidate,)),)
    )


def test_suspended_human_cannot_replace_a_grantor() -> None:
    candidate = replace(CANDIDATE, principal=replace(HUMAN, status=PrincipalStatus.SUSPENDED))
    assert not ProjectDeparturePolicy.may_depart(
        (ProjectDepartureResponsibilityPolicyInput(False, False, (candidate,)),)
    )


def test_document_action_accepts_a_coherent_group_manager_alternative() -> None:
    manager = replace(CANDIDATE, can_grant=False, is_group_member=True, is_group_manager=True)
    responsibility = ProjectDepartureResponsibilityPolicyInput(False, True, (manager,))
    assert ProjectDeparturePolicy.may_depart((responsibility,))
    assert not ProjectDeparturePolicy.may_depart(
        (replace(responsibility, allows_group_manager=False),)
    )
    assert not ProjectDeparturePolicy.may_depart(
        (replace(responsibility, candidates=(replace(manager, is_group_member=False),)),)
    )


def test_group_management_requires_a_member_manager_even_when_another_human_can_grant() -> None:
    responsibility = ProjectDepartureResponsibilityPolicyInput(True, False, (CANDIDATE,))
    assert not ProjectDeparturePolicy.may_depart((responsibility,))
    manager = replace(CANDIDATE, is_group_member=True, is_group_manager=True)
    assert ProjectDeparturePolicy.may_depart((replace(responsibility, candidates=(manager,)),))
