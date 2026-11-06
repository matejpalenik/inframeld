from dataclasses import dataclass

from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class AccessActionGrantChangedAuditEventDTO:
    """Correlate one checked Access assignment transition without a permission snapshot."""

    organization_id: OrganizationId
    target: (
        OrganizationGrantTargetDTO | AccessGroupGrantTargetDTO | ApplicationAccountGrantTargetDTO
    )
    actor_principal_id: PrincipalId
    recipient_principal_id: PrincipalId
    action_id: ActionId
    before_can_grant: bool | None
    can_grant: bool | None
    operation_id: OperationId
