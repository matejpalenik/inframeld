from uuid import UUID

from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.policies.stranded_authority_repair_policy import (
    StrandedAuthorityRepairPolicy,
)
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


def test_only_an_eligible_human_member_can_receive_a_definitely_stranded_responsibility() -> None:
    eligible = PrincipalAccessPolicyInput(
        principal=Principal(
            PrincipalId(UUID(int=1)),
            OrganizationId(UUID(int=2)),
            PrincipalKind.HUMAN,
            PrincipalStatus.ACTIVE,
        ),
        has_pending_recovery=False,
        credential_is_current=True,
    )
    assert StrandedAuthorityRepairPolicy.may_assign(
        recipient_access=eligible,
        requires_project=True,
        is_project_member=True,
        project_status=ProjectStatus.ACTIVE,
        eligible_grantor_exists=False,
    )
    for grantor in (True, None):
        assert not StrandedAuthorityRepairPolicy.may_assign(
            recipient_access=eligible,
            requires_project=True,
            is_project_member=True,
            project_status=ProjectStatus.ACTIVE,
            eligible_grantor_exists=grantor,
        )
    assert not StrandedAuthorityRepairPolicy.may_assign(
        recipient_access=eligible,
        requires_project=True,
        is_project_member=False,
        project_status=ProjectStatus.ACTIVE,
        eligible_grantor_exists=False,
    )
