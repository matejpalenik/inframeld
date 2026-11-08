from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.revoke_invitation_command import (
    RevokeInvitationCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.invitation_revocation_result_dto import (
    InvitationRevocationResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class InvitationRevoker(Protocol):
    @abstractmethod
    async def revoke(
        self,
        *,
        access: AccessContextDTO,
        command: RevokeInvitationCommand,
        context: IdempotencyContextDTO,
    ) -> InvitationRevocationResultDTO:
        """Authorize current human administration before returning an original outcome.

        Fresh revocation checks the reviewed Organization revision. Marking an
        unrevoked invitation advances it once with audit, while an already-revoked
        invitation keeps it. Preserve consumption and every completed assignment.
        """
        ...
