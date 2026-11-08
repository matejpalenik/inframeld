from dataclasses import dataclass

from inframeld_backend.access.application.dtos.invitation_assignment_dto import (
    InvitationAssignmentDTO,
)
from inframeld_backend.access.application.dtos.project_membership_observation_dto import (
    ProjectMembershipObservationDTO,
)


@dataclass(frozen=True, slots=True)
class InvitationAssignmentFactsDTO:
    """Bind one exact intent to current target and issuer-authority observations."""

    intent: InvitationAssignmentDTO
    project: ProjectMembershipObservationDTO | None
    target_exists: bool
    actor_can_grant: bool
    actor_is_group_member: bool
    actor_is_group_manager: bool
