from dataclasses import dataclass
from uuid import UUID

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId


@dataclass(frozen=True, slots=True)
class ProviderCredentialBindingDTO:
    """Identify the exact stored slot and revision protected by authenticated encryption."""

    organization_id: OrganizationId
    project_id: ProjectId
    connection_id: ModelConnectionId
    credential_id: UUID
    revision: int
