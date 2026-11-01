from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class ProjectMetadataAuthorityRepairedAuditEventDTO:
    organization_id: OrganizationId
    project_id: ProjectId
    recipient_id: PrincipalId
    operation_id: OperationId
    operator_label: str
    reason: str
    before_revision: int
    after_revision: int
