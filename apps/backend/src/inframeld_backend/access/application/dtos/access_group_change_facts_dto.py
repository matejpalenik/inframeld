from dataclasses import dataclass

from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class AccessGroupChangeFactsDTO(AuthorizedOperationScope[ProjectId]):
    """Observe current management and recipient state after the coordination turn."""

    organization_id: OrganizationId
    project_id: ProjectId
    access_revision: int
    group_id: AccessGroupId
    action: ProjectActionFactsDTO
    recipient: Principal | None
    recipient_is_project_member: bool
    recipient_has_coherent_identity: bool
    recipient_has_pending_recovery: bool
    relationships: AccessGroupRelationships
