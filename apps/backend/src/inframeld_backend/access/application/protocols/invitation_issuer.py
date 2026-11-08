from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.issue_invitation_command import (
    IssueInvitationCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.invitation_issue_result_dto import (
    InvitationIssueResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class InvitationIssuer(Protocol):
    """Issue exact protected intent under current human authority and safe original replay."""

    @abstractmethod
    async def issue(
        self,
        *,
        access: AccessContextDTO,
        command: IssueInvitationCommand,
        context: IdempotencyContextDTO,
    ) -> InvitationIssueResultDTO:
        """Check current admission and complete assignment authority before original history.

        Fresh work also checks reviewed revisions and configured lifetime. Save
        digest-only intent, revision, audit and original metadata atomically. A
        completed original never retrieves or regenerates a token, even after expiry.
        """
        ...
