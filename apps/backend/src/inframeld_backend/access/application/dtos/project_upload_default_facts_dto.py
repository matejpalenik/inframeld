from dataclasses import dataclass

from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.upload_default_group_facts_dto import (
    UploadDefaultGroupFactsDTO,
)
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience


@dataclass(frozen=True, slots=True)
class ProjectUploadDefaultFactsDTO(AuthorizedOperationScope[ProjectId]):
    """Observe actor and complete current/proposed group facts after coordination."""

    organization_id: OrganizationId
    project_id: ProjectId
    access_revision: int
    action: ProjectActionFactsDTO
    audience: UploadAudience | None
    groups: tuple[UploadDefaultGroupFactsDTO, ...]
