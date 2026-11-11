from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ApplicationAccountDeletionFactsDTO:
    """Observe exact-account Delete authority under caller-held coordination locks."""

    organization_id: OrganizationId
    project_id: ProjectId
    installation_id: InstallationId
    actor: ProjectActionFactsDTO
    application_principal: Principal
    access_revision: int
    checked_at: datetime
