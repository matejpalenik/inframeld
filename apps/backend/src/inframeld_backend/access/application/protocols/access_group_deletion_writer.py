from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.deleted_access_group_dto import DeletedAccessGroupDTO
from inframeld_backend.shared.application.dtos.deletion_status_binding_dto import (
    DeletionStatusBindingDTO,
)


class AccessGroupDeletionWriter(Protocol):
    @abstractmethod
    async def delete(
        self,
        *,
        group: DeletedAccessGroupDTO,
        expected_project_revision: int,
        binding: DeletionStatusBindingDTO,
    ) -> None:
        """Remove actual group relationships before the unused group in the caller's transaction.

        Retire its Name, save original result and audit, and publish synchronous
        completion only after the physical row is removed. Restrictive references
        fail atomically. No future content reference producer is simulated here.
        """
        ...
