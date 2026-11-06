from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.create_access_group_command import (
    CreateAccessGroupCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_creation_result_dto import (
    AccessGroupCreationResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class AccessGroupCreator(Protocol):
    @abstractmethod
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateAccessGroupCommand,
        context: IdempotencyContextDTO,
    ) -> AccessGroupCreationResultDTO:
        """Create a group with its human creator as ordinary member and manager.

        Require current human Project creation authority before replay or writing.
        Own the short transaction and preserve the original creation receipt.
        """
        ...
