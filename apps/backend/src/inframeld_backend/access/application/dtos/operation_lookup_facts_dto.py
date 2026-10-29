from dataclasses import dataclass

from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class OperationLookupFactsDTO:
    """Observe current scope and grants without reading reservation history."""

    installation_id: InstallationId
    principal: Principal
    project_status: ProjectStatus | None
    is_project_member: bool
    has_exact_action_grant: bool
    can_grant_action: bool
    has_pending_recovery: bool
    oauth_credential_facts: HumanOAuthCredentialFactsDTO | None
