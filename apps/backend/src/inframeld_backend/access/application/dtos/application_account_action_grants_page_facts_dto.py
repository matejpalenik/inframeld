from dataclasses import dataclass

from inframeld_backend.access.application.dtos.application_account_action_grant_dto import (
    ApplicationAccountActionGrantDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ApplicationAccountActionGrantsPageFactsDTO:
    """Observe the current authority header even for an empty bounded assignment page."""

    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    application_principal_id: PrincipalId
    action_id: ActionId
    actor_can_grant: bool
    actor: ProjectActionFactsDTO
    items: tuple[ApplicationAccountActionGrantDTO, ...]
