from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.change_access_group_relationship_command import (
    ChangeAccessGroupRelationshipCommand,
)
from inframeld_backend.access.application.dtos.access_group_change_facts_dto import (
    AccessGroupChangeFactsDTO,
)
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class AccessGroupRelationshipWriter(Protocol):
    @abstractmethod
    async def save(
        self,
        *,
        facts: AccessGroupChangeFactsDTO,
        command: ChangeAccessGroupRelationshipCommand,
        operation_id: OperationId,
        after: AccessGroupRelationships,
    ) -> None:
        """Save the checked transition, revision, audit and original result without committing.

        Remove management before ordinary membership. No-op requests retain the
        reviewed revision and still retain their exact original business result.
        """
        ...
