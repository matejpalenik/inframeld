from dataclasses import dataclass

from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ProjectDeletionFactsDTO:
    """Observe current Delete-project scope and revision without certifying admission."""

    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    access_revision: int
    action: ProjectActionFactsDTO
