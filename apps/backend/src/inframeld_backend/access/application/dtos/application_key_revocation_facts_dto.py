from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ApplicationKeyRevocationFactsDTO(AuthorizedOperationScope[ProjectId]):
    """Observe current Revoke authority and the exact target under caller-held locks."""

    organization_id: OrganizationId
    project_id: ProjectId
    installation_id: InstallationId
    actor: ProjectActionFactsDTO
    application_principal: Principal
    metadata: ApplicationKeyMetadataDTO | None
    access_revision: int
    checked_at: datetime
