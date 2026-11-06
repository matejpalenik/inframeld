from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


@dataclass(frozen=True, slots=True)
class ApplicationAccountMetadataDTO:
    """Carry safe account metadata without credential or assignment inventories."""

    organization_id: OrganizationId
    project_id: ProjectId
    principal_id: PrincipalId
    name: ResourceName | None
    display_name: str
    status: PrincipalStatus
    created_at: datetime
    access_revision: int
