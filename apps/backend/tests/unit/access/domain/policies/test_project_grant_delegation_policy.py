from dataclasses import replace
from uuid import UUID

from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.project_grant_delegation_policy import (
    ProjectGrantDelegationPolicy,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


def _principal(
    number: int,
    *,
    organization: int = 1,
    kind: PrincipalKind = PrincipalKind.HUMAN,
    status: PrincipalStatus = PrincipalStatus.ACTIVE,
) -> Principal:
    return Principal(
        id=PrincipalId(UUID(int=number)),
        organization_id=OrganizationId(UUID(int=organization)),
        kind=kind,
        status=status,
    )


def _may_assign(
    *,
    actor: Principal | None = None,
    recipient: Principal | None = None,
    actor_is_member: bool = True,
    recipient_is_member: bool = True,
    actor_can_grant: bool = True,
) -> bool:
    return ProjectGrantDelegationPolicy.may_assign_use_only_to_human(
        actor=actor if actor is not None else _principal(1),
        recipient=recipient if recipient is not None else _principal(2),
        actor_is_project_member=actor_is_member,
        recipient_is_project_member=recipient_is_member,
        actor_can_grant_action=actor_can_grant,
    )


def test_active_grantor_can_assign_use_only_to_human_member() -> None:
    assert _may_assign()


def test_use_permission_alone_does_not_allow_delegation() -> None:
    assert not _may_assign(actor_can_grant=False)


def test_grant_requires_eligible_members_in_the_same_organization() -> None:
    assert not _may_assign(actor_is_member=False)
    assert not _may_assign(recipient_is_member=False)
    assert not _may_assign(actor=replace(_principal(1), status=PrincipalStatus.SUSPENDED))
    assert not _may_assign(recipient=replace(_principal(2), status=PrincipalStatus.SUSPENDED))
    assert not _may_assign(recipient=_principal(2, kind=PrincipalKind.APPLICATION))
    assert not _may_assign(recipient=_principal(2, organization=2))
