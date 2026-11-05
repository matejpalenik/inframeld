from dataclasses import dataclass

from inframeld_backend.access.application.enums.project_membership_change_kind import (
    ProjectMembershipChangeKind,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ProjectMembershipChangeResultDTO:
    """Describe the original committed result independently of current membership."""

    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    actor_principal_id: PrincipalId
    principal_id: PrincipalId
    change_kind: ProjectMembershipChangeKind
    access_revision: int
    changed: bool
    status_code: int
    operation: CompletedSynchronousOperationDTO
