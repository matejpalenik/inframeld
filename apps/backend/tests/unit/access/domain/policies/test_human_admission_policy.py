from dataclasses import replace

import pytest
from tests.support.human_admission_scenarios import ALICE, BOB, COMMAND, ORG

from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.human_admission_policy import HumanAdmissionPolicy
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId


@pytest.mark.parametrize(
    "active,recovery,current,grant,expected",
    [
        (True, False, True, True, True),
        (False, False, True, True, False),
        (True, True, True, True, False),
        (True, False, False, True, False),
        (True, False, True, False, False),
    ],
)
def test_only_current_human_with_use_authority_may_admit(
    active: bool,
    recovery: bool,
    current: bool,
    grant: bool,
    expected: bool,
) -> None:
    principal = replace(
        ALICE, status=PrincipalStatus.ACTIVE if active else PrincipalStatus.SUSPENDED
    )
    assert (
        HumanAdmissionPolicy.may_authorize(
            PrincipalAccessPolicyInput(
                principal=principal, has_pending_recovery=recovery, credential_is_current=current
            ),
            has_admit_users=grant,
        )
        is expected
    )


def test_application_cannot_admit_humans() -> None:
    assert not HumanAdmissionPolicy.may_authorize(
        PrincipalAccessPolicyInput(
            principal=replace(ALICE, kind=PrincipalKind.APPLICATION),
            has_pending_recovery=False,
            credential_is_current=True,
        ),
        has_admit_users=True,
    )


@pytest.mark.parametrize(
    "principal,blocked,expected",
    [
        (None, False, True),
        (BOB, False, True),
        (None, True, False),
        (BOB, True, False),
        (replace(BOB, status=PrincipalStatus.SUSPENDED), False, False),
        (replace(BOB, kind=PrincipalKind.APPLICATION), False, False),
        (replace(BOB, organization_id=OrganizationId(ALICE.id.value)), False, False),
    ],
)
def test_recipient_admission_never_restores_or_crosses_org(
    principal: Principal | None,
    blocked: bool,
    expected: bool,
) -> None:
    assert (
        HumanAdmissionPolicy.may_admit(
            principal=principal,
            organization_id=ORG,
            has_pending_recovery=blocked,
        )
        is expected
    )


@pytest.mark.parametrize("revision", [-1, True, 2**63])
def test_command_rejects_invalid_revision(revision: int) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(COMMAND, expected_access_revision=revision)
