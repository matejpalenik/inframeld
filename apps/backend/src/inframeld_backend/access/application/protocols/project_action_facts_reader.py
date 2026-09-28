"""Define the current-state read boundary used by project authorization."""

from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId


class ProjectActionFactsReader(Protocol):
    """Load current project facts inside the caller's transaction."""

    @abstractmethod
    async def read_action_facts(
        self, *, access: AccessContextDTO, action_id: ActionId, target: ProjectActionTargetDTO
    ) -> ProjectActionFactsDTO | None:
        """Return stored facts for this exact principal, project, and action.

        `AccessContextDTO` identifies an already authenticated local principal.
        Return `None` when the principal or project is missing, or the project
        belongs to another organization. Include inactive status and absent
        membership in the returned facts; policies decide their consequences.
        The organization ID comes from the matched project row.

        The caller owns the transaction. Do not commit it, cache permissions,
        or treat a returned facts object as proof of visibility or authority.
        """
        ...
