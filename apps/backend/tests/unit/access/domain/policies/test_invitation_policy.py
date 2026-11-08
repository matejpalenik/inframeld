"""Keep current revoke authority separate from fresh invitation state."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.invitation_policy import InvitationPolicy
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId

ORGANIZATION = OrganizationId(UUID(int=1))
ISSUER_ID = PrincipalId(UUID(int=2))
OTHER_ID = PrincipalId(UUID(int=3))
ISSUER = Principal(
    id=ISSUER_ID,
    organization_id=ORGANIZATION,
    kind=PrincipalKind.HUMAN,
    status=PrincipalStatus.ACTIVE,
)
ELIGIBLE = PrincipalAccessPolicyInput(
    principal=ISSUER,
    has_pending_recovery=False,
    credential_is_current=True,
)
NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "original_issuer,has_use,can_grant,expected",
    [
        (True, True, False, True),
        (True, True, True, True),
        (True, False, False, False),
        (True, False, True, False),
        (False, True, False, False),
        (False, True, True, True),
        (False, False, False, False),
        (False, False, True, False),
    ],
)
def test_current_use_suffices_only_for_the_exact_original_issuer(
    original_issuer: bool,
    has_use: bool,
    can_grant: bool,
    expected: bool,
) -> None:
    actor = replace(ISSUER, id=ISSUER_ID if original_issuer else OTHER_ID)

    assert (
        InvitationPolicy.may_revoke(
            replace(ELIGIBLE, principal=actor),
            organization_id=ORGANIZATION,
            issuer_principal_id=ISSUER_ID,
            has_admit_users=has_use,
            can_grant_admit_users=can_grant,
        )
        is expected
    )


@pytest.mark.parametrize("original_issuer", [False, True])
@pytest.mark.parametrize(
    "eligibility",
    [
        replace(ELIGIBLE, principal=replace(ISSUER, status=PrincipalStatus.SUSPENDED)),
        replace(ELIGIBLE, principal=replace(ISSUER, status=PrincipalStatus.RETIRED)),
        replace(ELIGIBLE, principal=replace(ISSUER, kind=PrincipalKind.APPLICATION)),
        replace(ELIGIBLE, has_pending_recovery=True),
        replace(ELIGIBLE, credential_is_current=False),
    ],
)
def test_old_issuance_or_delegation_never_overrides_current_eligibility(
    original_issuer: bool,
    eligibility: PrincipalAccessPolicyInput,
) -> None:
    actor = replace(eligibility.principal, id=ISSUER_ID if original_issuer else OTHER_ID)

    assert not InvitationPolicy.may_revoke(
        replace(eligibility, principal=actor),
        organization_id=ORGANIZATION,
        issuer_principal_id=ISSUER_ID,
        has_admit_users=True,
        can_grant_admit_users=True,
    )


@pytest.mark.parametrize("original_issuer", [False, True])
def test_original_or_delegating_human_must_belong_to_the_invitation_org(
    original_issuer: bool,
) -> None:
    actor = replace(
        ISSUER,
        id=ISSUER_ID if original_issuer else OTHER_ID,
        organization_id=OrganizationId(UUID(int=99)),
    )

    assert not InvitationPolicy.may_revoke(
        replace(ELIGIBLE, principal=actor),
        organization_id=ORGANIZATION,
        issuer_principal_id=ISSUER_ID,
        has_admit_users=True,
        can_grant_admit_users=True,
    )


@pytest.mark.parametrize(
    "expires_at,expected",
    [
        (NOW + timedelta(days=1), True),
        (NOW + timedelta(microseconds=1), True),
        (NOW, False),
        (NOW - timedelta(microseconds=1), False),
    ],
)
def test_fresh_consumption_requires_strictly_future_expiry(
    expires_at: datetime,
    expected: bool,
) -> None:
    assert (
        InvitationPolicy.may_consume(
            expires_at=expires_at,
            current_time=NOW,
            revoked_at=None,
            consumed_at=None,
        )
        is expected
    )


@pytest.mark.parametrize(
    "revoked_at,consumed_at",
    [
        (NOW, None),
        (None, NOW),
        (NOW, NOW),
        (NOW + timedelta(seconds=1), None),
        (None, NOW + timedelta(seconds=1)),
    ],
)
def test_positive_revocation_or_consumption_blocks_new_use_even_before_expiry(
    revoked_at: datetime | None,
    consumed_at: datetime | None,
) -> None:
    assert not InvitationPolicy.may_consume(
        expires_at=NOW + timedelta(days=1),
        current_time=NOW,
        revoked_at=revoked_at,
        consumed_at=consumed_at,
    )
