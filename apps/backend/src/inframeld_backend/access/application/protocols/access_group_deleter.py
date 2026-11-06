from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.delete_access_group_command import (
    DeleteAccessGroupCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_deletion_result_dto import (
    AccessGroupDeletionResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.value_objects.request_id import RequestId


class AccessGroupDeleter(Protocol):
    @abstractmethod
    async def delete(
        self,
        *,
        access: AccessContextDTO,
        command: DeleteAccessGroupCommand,
        context: IdempotencyContextDTO,
        request_id: RequestId,
    ) -> AccessGroupDeletionResultDTO:
        """Delete an unused group atomically under current human management authority.

        Ordinary replay retains that authority requirement. Once the group is
        gone, only narrow initiator status recovery is available from the saved
        request identity or operation ID, never a full receipt or inventory.
        """
        ...
