"""Require eligible admitted human authority without inventing Project membership."""

from dataclasses import replace
from uuid import UUID

import pytest

from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.organization_grant_policy import (
    OrganizationGrantPolicy,
)
from inframeld_backend.access.domain.policy_inputs.organization_grant_candidate_policy_input import (
    OrganizationGrantCandidatePolicyInput,
)
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId

HUMAN = Principal(
    id=PrincipalId(UUID(int=1)),
    organization_id=OrganizationId(UUID(int=2)),
    kind=PrincipalKind.HUMAN,
    status=PrincipalStatus.ACTIVE,
)
ELIGIBLE = PrincipalAccessPolicyInput(
    principal=HUMAN, has_pending_recovery=False, credential_is_current=True
)
CANDIDATE = OrganizationGrantCandidatePolicyInput(
    principal=HUMAN,
    has_pending_recovery=False,
    has_coherent_identity=True,
    can_grant=True,
)


@pytest.mark.parametrize("action", list(OrganizationAction))
def test_only_the_four_organization_actions_are_supported(action: OrganizationAction) -> None:
    assert OrganizationGrantPolicy.supports_action(ActionId(action.value))


def test_project_and_unknown_actions_are_not_organization_authority() -> None:
    assert not OrganizationGrantPolicy.supports_action(ActionId("create-access-groups"))
    assert not OrganizationGrantPolicy.supports_action(ActionId("future-action"))


@pytest.mark.parametrize(
    "kind,status,pending,current,delegation,expected",
    [
        (PrincipalKind.HUMAN, PrincipalStatus.ACTIVE, False, True, True, True),
        (PrincipalKind.APPLICATION, PrincipalStatus.ACTIVE, False, True, True, False),
        (PrincipalKind.HUMAN, PrincipalStatus.SUSPENDED, False, True, True, False),
        (PrincipalKind.HUMAN, PrincipalStatus.ACTIVE, True, True, True, False),
        (PrincipalKind.HUMAN, PrincipalStatus.ACTIVE, False, False, True, False),
        (PrincipalKind.HUMAN, PrincipalStatus.ACTIVE, False, True, False, False),
    ],
)
def test_management_requires_current_eligible_human_delegation(
    kind: PrincipalKind,
    status: PrincipalStatus,
    pending: bool,
    current: bool,
    delegation: bool,
    expected: bool,
) -> None:
    actor = PrincipalAccessPolicyInput(
        principal=replace(HUMAN, kind=kind, status=status),
        has_pending_recovery=pending,
        credential_is_current=current,
    )

    assert (
        OrganizationGrantPolicy.may_manage(actor_access=actor, can_grant_action=delegation)
        is expected
    )


@pytest.mark.parametrize("change", ["eligible", "application", "suspended", "recovery", "identity"])
def test_fresh_assignment_requires_a_coherent_eligible_human(change: str) -> None:
    recipient = replace(
        ELIGIBLE,
        principal=replace(
            HUMAN,
            kind=PrincipalKind.APPLICATION if change == "application" else PrincipalKind.HUMAN,
            status=PrincipalStatus.SUSPENDED if change == "suspended" else PrincipalStatus.ACTIVE,
        ),
        has_pending_recovery=change == "recovery",
    )

    assert OrganizationGrantPolicy.may_receive(
        recipient_access=recipient, has_coherent_identity=change != "identity"
    ) is (change == "eligible")


@pytest.mark.parametrize(
    "change", ["eligible", "application", "suspended", "recovery", "identity", "use-only"]
)
def test_handover_requires_an_eligible_exact_action_grantor(change: str) -> None:
    candidate = replace(
        CANDIDATE,
        principal=replace(
            HUMAN,
            kind=PrincipalKind.APPLICATION if change == "application" else PrincipalKind.HUMAN,
            status=PrincipalStatus.SUSPENDED if change == "suspended" else PrincipalStatus.ACTIVE,
        ),
        has_pending_recovery=change == "recovery",
        has_coherent_identity=change != "identity",
        can_grant=change != "use-only",
    )

    assert OrganizationGrantPolicy.has_remaining_grantor((candidate,)) is (change == "eligible")


def test_handover_cannot_use_an_empty_candidate_set() -> None:
    assert not OrganizationGrantPolicy.has_remaining_grantor(())


def test_an_ineligible_candidate_does_not_hide_an_eligible_replacement() -> None:
    assert OrganizationGrantPolicy.has_remaining_grantor(
        (replace(CANDIDATE, has_pending_recovery=True), CANDIDATE)
    )
