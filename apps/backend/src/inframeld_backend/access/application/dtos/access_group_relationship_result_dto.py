from dataclasses import dataclass

from inframeld_backend.access.application.enums.access_group_change_kind import (
    AccessGroupChangeKind,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True)
class AccessGroupRelationshipResultDTO:
    """Keep the original transition without restoring relationships on replay."""

    organization_id: OrganizationId
    project_id: ProjectId
    group_id: AccessGroupId
    actor_principal_id: PrincipalId
    principal_id: PrincipalId
    change_kind: AccessGroupChangeKind
    access_revision: int
    changed: bool
    relationships: AccessGroupRelationships
    status_code: int
    operation: CompletedSynchronousOperationDTO
