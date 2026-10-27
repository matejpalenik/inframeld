from itertools import product
from uuid import UUID

import pytest

from inframeld_backend.access.domain.entities.identity_recovery import IdentityRecovery
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.identity_recovery_release_policy import (
    IdentityRecoveryReleasePolicy,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


def _recovery(
    kratos: IdentityRecoveryCleanupState = IdentityRecoveryCleanupState.CONFIRMED,
    hydra: IdentityRecoveryCleanupState = IdentityRecoveryCleanupState.CONFIRMED,
) -> IdentityRecovery:
    return IdentityRecovery(
        installation_id=InstallationId(UUID(int=1)),
        authority=IdentityAuthority("kratos"),
        flow_id=IdentityRecoveryFlowId(UUID(int=2)),
        subject=IdentitySubject("alice"),
        kratos_cleanup_state=kratos,
        hydra_cleanup_state=hydra,
    )


@pytest.mark.parametrize(("kratos", "hydra"), list(product(IdentityRecoveryCleanupState, repeat=2)))
def test_unlinked_identity_finishes_only_after_both_cleanups_are_confirmed(
    kratos: IdentityRecoveryCleanupState, hydra: IdentityRecoveryCleanupState
) -> None:
    """Cleanup can finish before local admission, but failure or uncertainty keeps its block."""
    assert IdentityRecoveryReleasePolicy.may_release(
        recovery=_recovery(kratos, hydra), principal=None
    ) is (
        kratos is IdentityRecoveryCleanupState.CONFIRMED
        and hydra is IdentityRecoveryCleanupState.CONFIRMED
    )


@pytest.mark.parametrize("kind", list(PrincipalKind))
@pytest.mark.parametrize("status", list(PrincipalStatus))
def test_linked_account_must_be_an_active_human(
    kind: PrincipalKind, status: PrincipalStatus
) -> None:
    """Finishing a password recovery cannot restore suspension or act for an application."""
    principal = Principal(
        id=PrincipalId(UUID(int=3)),
        organization_id=OrganizationId(UUID(int=4)),
        kind=kind,
        status=status,
    )

    assert IdentityRecoveryReleasePolicy.may_release(recovery=_recovery(), principal=principal) is (
        kind is PrincipalKind.HUMAN and status is PrincipalStatus.ACTIVE
    )
