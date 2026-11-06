from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.remove_application_account_action_grant_command import (
    RemoveApplicationAccountActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_application_account_action_grant_command import (
    SetApplicationAccountActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_action_grant_change_result_dto import (
    ApplicationAccountActionGrantChangeResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class ApplicationAccountActionGrantChanger(Protocol):
    """Change one exact grant under current human delegation and caller-owned retry identity.

    Implementations own a short transaction and require a clean request-local
    session. Authorize before history. Fresh work checks revision, recipient and
    handover. Commit grant, revision, audit and original result together. No-op
    retains a safe original result without change audit or revision advancement.
    """

    @abstractmethod
    async def set_grant(
        self,
        *,
        access: AccessContextDTO,
        command: SetApplicationAccountActionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationAccountActionGrantChangeResultDTO:
        """Set use-only or delegating authority for an eligible admitted human."""
        ...

    @abstractmethod
    async def remove_grant(
        self,
        *,
        access: AccessContextDTO,
        command: RemoveApplicationAccountActionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationAccountActionGrantChangeResultDTO:
        """Remove an exact assignment, including from a suspended or blocked human.

        Retain current actor authority, recipient scope and safe last-grantor
        handover. Replay returns its original absence without removing a regrant.
        """
        ...
