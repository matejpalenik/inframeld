from dataclasses import dataclass

from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_action_grant_assignment_dto import (
    OrganizationActionGrantAssignmentDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class OrganizationActionGrantsPageFactsDTO:
    """Observe the current authority header even for an empty bounded assignment page."""

    installation_id: InstallationId
    organization_id: OrganizationId
    action_id: ActionId
    actor_can_grant: bool
    actor: Principal
    actor_has_pending_recovery: bool
    actor_oauth_credential_facts: HumanCredentialFactsDTO | None
    items: tuple[OrganizationActionGrantAssignmentDTO, ...]
