from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience


@dataclass(frozen=True, slots=True)
class ProjectUploadDefaultDTO:
    organization_id: OrganizationId
    project_id: ProjectId
    access_revision: int
    audience: UploadAudience | None
