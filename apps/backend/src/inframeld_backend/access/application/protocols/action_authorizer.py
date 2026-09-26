"""Define the application operation used to require current project authority."""

from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId


class ActionAuthorizer(Protocol):
    """Require current visibility and an exact action grant on a project."""

    @abstractmethod
    async def require_action(
        self, *, access: AccessContextDTO, action: ActionId, target: ProjectActionTargetDTO
    ) -> None:
        """Read current facts and deny hidden targets with ResourceNotFoundError.

        Raise `AccessDeniedError` for visible targets lacking authority. Grant
        decisions are never cached on the caller's authentication context.
        Success returns None and means the current facts permitted this exact
        action. It grants no future authority after the caller's state changes.
        The caller owns the surrounding transaction; this operation does not
        open a transaction, commit changes, or provision permissions.
        """
        ...
