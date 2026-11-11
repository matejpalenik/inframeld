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
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class StrandedAuthorityRepairResultDTO:
    operation_id: OperationId
    installation_id: InstallationId
    organization_id: OrganizationId
    responsibility: GroupManagerRepairResponsibilityDTO | ActionGrantorRepairResponsibilityDTO
    recipient_id: PrincipalId
    access_revision: int
