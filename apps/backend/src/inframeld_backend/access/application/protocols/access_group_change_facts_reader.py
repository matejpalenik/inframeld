from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.change_access_group_relationship_command import (
    ChangeAccessGroupRelationshipCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_change_facts_dto import (
    AccessGroupChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.project_departure_candidate_dto import (
    ProjectDepartureCandidateDTO,
)


class AccessGroupChangeFactsReader(Protocol):
    @abstractmethod
    async def lock_for_change(
        self, *, access: AccessContextDTO, command: ChangeAccessGroupRelationshipCommand
    ) -> AccessGroupChangeFactsDTO | None:
        """Read scoped actor, recipient and relationships after taking the write turn."""
        ...

    @abstractmethod
    async def remaining_managers(
        self, *, facts: AccessGroupChangeFactsDTO, command: ChangeAccessGroupRelationshipCommand
    ) -> tuple[ProjectDepartureCandidateDTO, ...]:
        """Read current replacement humans, excluding the departing manager."""
        ...
