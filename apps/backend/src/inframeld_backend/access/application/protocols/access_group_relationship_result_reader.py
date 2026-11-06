from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.change_access_group_relationship_command import (
    ChangeAccessGroupRelationshipCommand,
)
from inframeld_backend.access.application.dtos.access_group_change_facts_dto import (
    AccessGroupChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.access_group_relationship_result_dto import (
    AccessGroupRelationshipResultDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


class AccessGroupRelationshipResultReader(Protocol):
    @abstractmethod
    async def original(
        self,
        *,
        facts: AccessGroupChangeFactsDTO,
        command: ChangeAccessGroupRelationshipCommand,
        operation: CompletedSynchronousOperationDTO,
    ) -> AccessGroupRelationshipResultDTO:
        """Read the exact original transition after current management authorization."""
        ...
