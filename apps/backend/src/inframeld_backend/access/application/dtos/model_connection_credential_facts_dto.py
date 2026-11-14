from dataclasses import dataclass

from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.application.dtos.model_connection_credential_dto import (
    ModelConnectionCredentialDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class ModelConnectionCredentialFactsDTO(AuthorizedOperationScope[ProjectId]):
    organization_id: OrganizationId
    project_id: ProjectId
    action: ProjectActionFactsDTO
    connection_access: ModelConnectionAccessDTO
    credential: ModelConnectionCredentialDTO
    key_id: str | None
