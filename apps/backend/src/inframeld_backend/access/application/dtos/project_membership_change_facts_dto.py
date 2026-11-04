from dataclasses import dataclass

from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_departure_responsibility_dto import (
    ProjectDepartureResponsibilityDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ProjectMembershipChangeFactsDTO:
    """Observe actor, recipient and departure dependencies under Access coordination."""

    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    access_revision: int
    action: ProjectActionFactsDTO
    recipient: Principal | None
    recipient_has_pending_recovery: bool
    recipient_has_coherent_identity: bool
    recipient_is_project_member: bool
    responsibilities: tuple[ProjectDepartureResponsibilityDTO, ...] = ()
