from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.issue_application_key_command import (
    IssueApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_issue_result_dto import (
    ApplicationKeyIssueResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class ApplicationKeyIssuer(Protocol):
    """Issue once under current human authority and recover only the safe original.

    Fresh issuance checks every selected trusted profile and the current lifetime
    and usable-key limits. A completed original precedes those fresh checks.
    Uncertain completion never authorizes automatic replacement or secret replay.
    """

    @abstractmethod
    async def issue(
        self,
        *,
        access: AccessContextDTO,
        command: IssueApplicationKeyCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationKeyIssueResultDTO: ...
