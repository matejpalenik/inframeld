from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


@dataclass(frozen=True, slots=True)
class AccessGroupMetadataDTO:
    organization_id: OrganizationId
    project_id: ProjectId
    group_id: AccessGroupId
    name: ResourceName | None
    display_name: str
    created_at: datetime
    access_revision: int
