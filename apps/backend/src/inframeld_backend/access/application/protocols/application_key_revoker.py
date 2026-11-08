from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.revoke_application_key_command import (
    RevokeApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_revocation_result_dto import (
    ApplicationKeyRevocationResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class ApplicationKeyRevoker(Protocol):
    """Revoke an exact key under independent current human Revoke authority.

    Authorize before recovering history. Only fresh work checks the reviewed
    revision. Already-revoked keys retain their timestamp and revision. Historical
    replay returns its immutable receipt, never plaintext or a replacement key.
    Known rollback and uncertain commit acknowledgment retain different meanings.
    """

    @abstractmethod
    async def revoke(
        self,
        *,
        access: AccessContextDTO,
        command: RevokeApplicationKeyCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationKeyRevocationResultDTO: ...
