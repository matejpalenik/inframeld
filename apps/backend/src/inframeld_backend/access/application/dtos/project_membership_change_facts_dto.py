from dataclasses import dataclass

from inframeld_backend.access.application.dtos.project_membership_observation_dto import (
    ProjectMembershipObservationDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal


@dataclass(frozen=True, slots=True)
class ProjectMembershipChangeFactsDTO(ProjectMembershipObservationDTO):
    """Observe actor and recipient state under Access coordination."""

    recipient: Principal | None
    recipient_has_pending_recovery: bool
    recipient_has_coherent_identity: bool
    recipient_is_project_member: bool
