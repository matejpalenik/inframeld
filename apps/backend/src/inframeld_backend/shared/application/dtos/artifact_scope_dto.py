from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ArtifactScopeDTO:
    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
