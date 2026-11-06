"""Keep the three concrete target catalogues and current human authority distinct."""

from dataclasses import replace
from uuid import UUID

import pytest

from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.access_group_grant_policy import (
    AccessGroupGrantPolicy,
)
from inframeld_backend.access.domain.policies.application_account_grant_policy import (
    ApplicationAccountGrantPolicy,
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
    principal=HUMAN,
    has_pending_recovery=False,
    credential_is_current=True,
)


@pytest.mark.parametrize("action", ["add-documents", "update-documents", "delete-documents"])
@pytest.mark.parametrize("level", [False, True])
def test_group_human_receives_either_level_but_application_receives_only_use(
    action: str, level: bool
) -> None:
    assert AccessGroupGrantPolicy.supports_recipient(
        action_id=ActionId(action),
        kind=PrincipalKind.HUMAN,
        can_grant=level,
    )
    assert AccessGroupGrantPolicy.supports_recipient(
        action_id=ActionId(action),
        kind=PrincipalKind.APPLICATION,
        can_grant=level,
    ) is (not level)


def test_target_catalogues_do_not_accept_other_target_actions() -> None:
    assert not AccessGroupGrantPolicy.supports_recipient(
        action_id=ActionId("issue-application-keys"),
        kind=PrincipalKind.HUMAN,
        can_grant=True,
    )
    assert not ApplicationAccountGrantPolicy.supports_recipient(
        action_id=ActionId("add-documents"),
        kind=PrincipalKind.HUMAN,
    )


@pytest.mark.parametrize(
    "action", ["issue-application-keys", "revoke-application-keys", "delete-application-account"]
)
def test_application_administration_assignments_are_human_only(action: str) -> None:
    assert ApplicationAccountGrantPolicy.supports_recipient(
        action_id=ActionId(action), kind=PrincipalKind.HUMAN
    )
    assert not ApplicationAccountGrantPolicy.supports_recipient(
        action_id=ActionId(action), kind=PrincipalKind.APPLICATION
    )


@pytest.mark.parametrize(
    "delegation,member,manager,expected",
    [
        (True, False, False, True),
        (False, True, True, True),
        (False, True, False, False),
        (False, False, True, False),
    ],
)
def test_group_management_alternative_requires_both_group_relationships(
    delegation: bool, member: bool, manager: bool, expected: bool
) -> None:
    assert (
        AccessGroupGrantPolicy.may_manage(
            actor_access=ELIGIBLE,
            is_project_member=True,
            can_grant_action=delegation,
            is_group_member=member,
            is_group_manager=manager,
        )
        is expected
    )
    assert not AccessGroupGrantPolicy.may_manage(
        actor_access=ELIGIBLE,
        is_project_member=False,
        can_grant_action=delegation,
        is_group_member=member,
        is_group_manager=manager,
    )


@pytest.mark.parametrize(
    "access",
    [
        replace(ELIGIBLE, principal=replace(HUMAN, status=PrincipalStatus.SUSPENDED)),
        replace(ELIGIBLE, has_pending_recovery=True),
        replace(ELIGIBLE, credential_is_current=False),
        replace(ELIGIBLE, principal=replace(HUMAN, kind=PrincipalKind.APPLICATION)),
    ],
)
def test_group_manager_is_not_a_substitute_for_current_eligible_human(
    access: PrincipalAccessPolicyInput,
) -> None:
    assert not AccessGroupGrantPolicy.may_manage(
        actor_access=access,
        is_project_member=True,
        can_grant_action=True,
        is_group_member=True,
        is_group_manager=True,
    )


@pytest.mark.parametrize(
    "member,coherent,pending,active,expected",
    [
        (True, True, False, True, True),
        (False, True, False, True, False),
        (True, False, False, True, False),
        (True, True, True, True, False),
        (True, True, False, False, False),
    ],
)
def test_new_human_target_grants_require_current_admitted_project_membership(
    member: bool, coherent: bool, pending: bool, active: bool, expected: bool
) -> None:
    access = replace(
        ELIGIBLE,
        has_pending_recovery=pending,
        principal=replace(
            HUMAN, status=PrincipalStatus.ACTIVE if active else PrincipalStatus.SUSPENDED
        ),
    )
    assert (
        AccessGroupGrantPolicy.may_receive(
            recipient_access=access,
            is_project_member=member,
            has_coherent_identity=coherent,
            application_is_bound=False,
        )
        is expected
    )
    assert (
        ApplicationAccountGrantPolicy.may_receive(
            recipient_access=access,
            is_project_member=member,
            has_coherent_identity=coherent,
        )
        is expected
    )


def test_application_group_recipient_needs_current_immutable_project_binding() -> None:
    application = replace(ELIGIBLE, principal=replace(HUMAN, kind=PrincipalKind.APPLICATION))
    for bound in (False, True):
        assert (
            AccessGroupGrantPolicy.may_receive(
                recipient_access=application,
                is_project_member=True,
                has_coherent_identity=False,
                application_is_bound=bound,
            )
            is bound
        )
    assert not ApplicationAccountGrantPolicy.may_receive(
        recipient_access=application,
        is_project_member=True,
        has_coherent_identity=True,
    )
