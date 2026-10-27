from dataclasses import dataclass

from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.project_status import ProjectStatus


@dataclass(frozen=True, slots=True)
class ProjectActionFactsDTO:
    """Current caller and project facts for one authorization attempt.

    The reader establishes the organization match. The service decides
    visibility and permission from these facts.
    """

    principal: Principal
    has_pending_recovery: bool
    oauth_credential_facts: HumanOAuthCredentialFactsDTO | None
    project_status: ProjectStatus
    is_project_member: bool
    has_exact_action_grant: bool
