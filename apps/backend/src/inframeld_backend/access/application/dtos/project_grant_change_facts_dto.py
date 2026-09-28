from dataclasses import dataclass

from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.project_status import ProjectStatus


@dataclass(frozen=True, slots=True)
class ProjectGrantChangeFactsDTO:
    """Current facts read while the project's Access change lock is held."""

    actor: Principal
    recipient: Principal | None
    project_status: ProjectStatus
    project_access_revision: int
    actor_is_project_member: bool
    recipient_is_project_member: bool
    actor_can_grant_action: bool
