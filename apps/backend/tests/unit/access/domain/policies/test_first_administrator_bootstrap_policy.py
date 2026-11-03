from uuid import UUID

import pytest

from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.first_administrator_bootstrap_policy import (
    FirstAdministratorBootstrapPolicy,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@pytest.mark.parametrize(
    ("kind", "status", "pending", "allowed"),
    [
        (None, None, False, True),
        (None, None, True, False),
        (PrincipalKind.HUMAN, PrincipalStatus.ACTIVE, False, True),
        (PrincipalKind.HUMAN, PrincipalStatus.ACTIVE, True, False),
        (PrincipalKind.HUMAN, PrincipalStatus.SUSPENDED, False, False),
        (PrincipalKind.HUMAN, PrincipalStatus.RETIRED, False, False),
        (PrincipalKind.APPLICATION, PrincipalStatus.ACTIVE, False, False),
    ],
)
def test_first_admission_does_not_require_or_restore_a_local_account(
    kind: PrincipalKind | None, status: PrincipalStatus | None, pending: bool, allowed: bool
) -> None:
    principal = (
        Principal(PrincipalId(UUID(int=1)), OrganizationId(UUID(int=2)), kind, status)
        if kind is not None and status is not None
        else None
    )

    assert (
        FirstAdministratorBootstrapPolicy.may_admit(
            principal=principal, has_pending_recovery=pending
        )
        is allowed
    )
