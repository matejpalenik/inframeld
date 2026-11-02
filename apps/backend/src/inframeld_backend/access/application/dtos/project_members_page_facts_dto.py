from dataclasses import dataclass

from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_member_dto import ProjectMemberDTO
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ProjectMembersPageFactsDTO:
    """Observe current authority, revision and bounded rows from one SQL snapshot.

    The header survives an empty continuation. These facts do not authorize
    disclosure until the application checks the current caller and exact scope.
    """

    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    access_revision: int
    action: ProjectActionFactsDTO
    members: tuple[ProjectMemberDTO, ...]
