"""Define the current-state read boundary used by project authorization."""

from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.access_context import AccessContext
from inframeld_backend.access.application.authorization.current_action_facts import (
    CurrentActionFacts,
)
from inframeld_backend.access.application.authorization.project_action_target import (
    ProjectActionTarget,
)
from inframeld_backend.access.domain.action_values import ActionId


class ActionFactsReader(Protocol):
    """Load current project facts inside the caller's transaction."""

    @abstractmethod
    async def read_action_facts(
        self, *, access: AccessContext, action: ActionId, target: ProjectActionTarget
    ) -> CurrentActionFacts | None:
        """Return stored facts for this exact principal, project, and action.

        AccessContext identifies an already authenticated local principal.
        Return None when the principal or project is missing, or the project
        belongs to another organization. Include inactive status and absent
        membership in the returned facts; policies decide their consequences.

        The caller owns the transaction. Do not commit it, cache permissions,
        or treat a returned facts object as proof of visibility or authority.
        """
        ...
