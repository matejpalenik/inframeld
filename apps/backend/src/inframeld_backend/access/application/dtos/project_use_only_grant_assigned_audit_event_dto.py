from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class ProjectUseOnlyGrantAssignedAuditEventDTO:
    """Describe one authorized assignment for atomic Access audit persistence."""

    organization_id: OrganizationId
    project_id: ProjectId
    actor_principal_id: PrincipalId
    recipient_principal_id: PrincipalId
    action_id: ActionId
    operation_id: OperationId
