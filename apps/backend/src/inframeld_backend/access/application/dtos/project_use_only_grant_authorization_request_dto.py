from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class ProjectUseOnlyGrantAuthorizationRequestDTO:
    """Identify the assignment to check - action names the permission being delegated."""

    project_id: ProjectId
    recipient_principal_id: PrincipalId
    action_id: ActionId
