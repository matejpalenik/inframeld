from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.change_access_group_relationship_command import (
    ChangeAccessGroupRelationshipCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_relationship_result_dto import (
    AccessGroupRelationshipResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class AccessGroupRelationshipChanger(Protocol):
    @abstractmethod
    async def change(
        self,
        *,
        access: AccessContextDTO,
        command: ChangeAccessGroupRelationshipCommand,
        context: IdempotencyContextDTO,
    ) -> AccessGroupRelationshipResultDTO:
        """Change membership or management after current human manager authorization.

        Coordinate Organization shared then Project exclusive. Check authority
        before replay, and fresh eligibility and last-manager protection before
        the atomic relationships, audit, revision and original result write.
        """
        ...
