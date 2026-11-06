from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.remove_project_action_grant_command import (
    RemoveProjectActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_project_action_grant_command import (
    SetProjectActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_grant_change_result_dto import (
    ProjectActionGrantChangeResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)


class ProjectGrantChanger(Protocol):
    """Give a human permission to perform a named action in one project.

    The caller requests the change. The recipient is the person receiving the
    permission. Implementations own the database transaction and require a
    request-local session with no active transaction when the call starts.
    """

    @abstractmethod
    async def set_action_grant(
        self,
        *,
        access: AccessContextDTO,
        command: SetProjectActionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectActionGrantChangeResultDTO:
        """Set an eligible exact assignment under current human delegation.

        Authorize actor/scope before reservation or completed replay. Only new
        work checks recipient eligibility, reviewed Access revision and handover.
        Commit change/revision/audit/original result together. New assignment is
        201, level change or no-op is 200. Replay returns original status/facts.
        """
        ...

    @abstractmethod
    async def remove_action_grant(
        self,
        *,
        access: AccessContextDTO,
        command: RemoveProjectActionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectActionGrantChangeResultDTO:
        """Remove only this action, including from an inactive/blocked recipient.

        Retain current actor authority and exact recipient scope. New work checks
        reviewed Access revision and remaining eligible exact-action grantors.
        An authorized absent result is 200 without a revision increment. Replay
        returns original removal facts and never removes a later assignment.
        """
        ...
