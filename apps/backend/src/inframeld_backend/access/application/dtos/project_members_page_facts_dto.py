from dataclasses import dataclass

from inframeld_backend.access.application.dtos.project_member_dto import ProjectMemberDTO
from inframeld_backend.access.application.dtos.project_membership_observation_dto import (
    ProjectMembershipObservationDTO,
)


@dataclass(frozen=True, slots=True)
class ProjectMembersPageFactsDTO(ProjectMembershipObservationDTO):
    """Observe current authority, revision and bounded rows from one SQL snapshot.

    The header survives an empty continuation. These facts do not authorize
    disclosure until the application checks the current caller and exact scope.
    """

    members: tuple[ProjectMemberDTO, ...]
