from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class ProjectUploadDefaultRecordDTO:
    """Retain private before/after snapshots without pinning mutable groups."""

    operation_id: OperationId
    organization_id: OrganizationId
    project_id: ProjectId
    actor_principal_id: PrincipalId
    before_revision: int
    access_revision: int
    before_audience: UploadAudience | None
    audience: UploadAudience
