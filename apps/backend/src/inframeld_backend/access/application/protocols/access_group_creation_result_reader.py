from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.created_access_group_dto import (
    CreatedAccessGroupDTO,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class AccessGroupCreationResultReader(Protocol):
    @abstractmethod
    async def original(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_id: PrincipalId,
        operation_id: OperationId,
    ) -> CreatedAccessGroupDTO:
        """Read immutable original facts under current creation authority and expiry.

        Reject a missing or incoherent result. Do not reconstruct names or grants
        from today's account or extend the reservation's replay lifetime.
        """
        ...
