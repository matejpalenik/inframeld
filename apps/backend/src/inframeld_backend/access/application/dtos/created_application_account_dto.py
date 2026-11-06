from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


@dataclass(frozen=True, slots=True)
class CreatedApplicationAccountDTO:
    """Retain original account creation facts, independent of today's assignments."""

    operation_id: OperationId
    organization_id: OrganizationId
    project_id: ProjectId
    principal_id: PrincipalId
    creator_principal_id: PrincipalId
    name: ResourceName
    display_name: str
    access_revision: int
    initial_actions: tuple[ActionId, ...]
