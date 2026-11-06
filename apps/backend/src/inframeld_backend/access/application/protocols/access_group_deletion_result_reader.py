from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.delete_access_group_command import (
    DeleteAccessGroupCommand,
)
from inframeld_backend.access.application.dtos.deleted_access_group_dto import DeletedAccessGroupDTO
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class AccessGroupDeletionResultReader(Protocol):
    @abstractmethod
    async def original(
        self,
        *,
        organization_id: OrganizationId,
        actor_id: PrincipalId,
        command: DeleteAccessGroupCommand,
        operation_id: OperationId,
    ) -> DeletedAccessGroupDTO:
        """Read the ordinary original receipt after current group management authorization."""
        ...
