from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


@dataclass(frozen=True, slots=True)
class ProjectMetadataDTO:
    organization_id: OrganizationId
    project_id: ProjectId
    name: ResourceName | None
    display_name: str
    metadata_revision: int
