from dataclasses import dataclass

from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.project_status import ProjectStatus


@dataclass(frozen=True, slots=True)
class ProjectGrantChangeFactsDTO:
    """Current grant facts observed while the Access change locks are held."""

    actor: Principal
    has_pending_recovery: bool
    oauth_credential_facts: HumanOAuthCredentialFactsDTO | None
    recipient: Principal | None
    project_status: ProjectStatus
    project_access_revision: int
    actor_is_project_member: bool
    recipient_is_project_member: bool
    actor_can_grant_action: bool
