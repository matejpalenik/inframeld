from dataclasses import dataclass

from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class AdmittedWorkFactsDTO:
    principal: Principal
    installation_id: InstallationId
    project_status: ProjectStatus
    is_project_member: bool
    has_exact_action_grant: bool
    has_pending_recovery: bool
    human_generation: HumanOAuthCredentialFactsDTO | None
