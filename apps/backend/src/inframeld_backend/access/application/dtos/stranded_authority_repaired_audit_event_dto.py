from dataclasses import dataclass

from inframeld_backend.access.application.dtos.action_grantor_repair_responsibility_dto import (
    ActionGrantorRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.group_manager_repair_responsibility_dto import (
    GroupManagerRepairResponsibilityDTO,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class StrandedAuthorityRepairedAuditEventDTO:
    organization_id: OrganizationId
    recipient_id: PrincipalId
    responsibility: GroupManagerRepairResponsibilityDTO | ActionGrantorRepairResponsibilityDTO
    operation_id: OperationId
    operator_label: str
    reason: str
    before_revision: int
    after_revision: int
