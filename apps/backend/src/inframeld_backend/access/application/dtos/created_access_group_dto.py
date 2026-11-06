from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


@dataclass(frozen=True, slots=True)
class CreatedAccessGroupDTO:
    """Retain original creation independently of later membership or deletion."""

    operation_id: OperationId
    organization_id: OrganizationId
    project_id: ProjectId
    group_id: AccessGroupId
    creator_principal_id: PrincipalId
    name: ResourceName
    display_name: str
    access_revision: int
