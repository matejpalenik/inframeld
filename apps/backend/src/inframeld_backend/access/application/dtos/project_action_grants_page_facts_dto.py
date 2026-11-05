from dataclasses import dataclass

from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_action_grant_dto import ProjectActionGrantDTO
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ProjectActionGrantsPageFactsDTO:
    """Observe a bounded assignment page with its current authority header."""

    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    action_id: ActionId
    action: ProjectActionFactsDTO
    actor_can_grant_action: bool
    items: tuple[ProjectActionGrantDTO, ...]
