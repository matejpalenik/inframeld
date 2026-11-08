from abc import abstractmethod
from datetime import datetime
from typing import Protocol

from inframeld_backend.access.application.dtos.invitation_record_dto import InvitationRecordDTO
from inframeld_backend.access.application.dtos.invitation_revocation_result_dto import (
    InvitationRevocationResultDTO,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


class InvitationWriter(Protocol):
    """Save invitation effects inside the authorized caller's transaction."""

    @abstractmethod
    async def save_issue(
        self, *, record: InvitationRecordDTO, expected_access_revision: int
    ) -> None:
        """Bind new intent to its exact in-progress native issuance reservation.

        The caller holds the Organization and reviewed sorted Project turns and has
        checked current human issuer authority for the complete intent. Preserve
        those scope/reservation guards, advance only the Organization revision and
        append audit atomically. No plaintext token or independent commit belongs here.
        """
        ...

    @abstractmethod
    async def save_revocation(
        self,
        *,
        invitation: InvitationRecordDTO,
        result: InvitationRevocationResultDTO,
        actor_principal_id: PrincipalId,
        expected_access_revision: int,
        revoked_at: datetime,
    ) -> None:
        """Atomically persist the checked revocation, audit and native original result.

        The caller holds the Organization turn and has authorized current human
        revocation before reserving or replaying. Validate the exact completed native
        reservation and original scope. Advance the Organization only when first
        marking revoked, preserving consumption, assignments and no-op revisions.
        """
        ...
