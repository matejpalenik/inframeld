from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.stranded_authority_repaired_audit_event_dto import (
    StrandedAuthorityRepairedAuditEventDTO,
)


class StrandedAuthorityAuditWriter(Protocol):
    """Save the exact host repair audit in the caller's assignment transaction.

    Metadata retains its existing event representation. Other responsibilities retain only
    the reviewed scope, recipient, attribution and revision, never recipient proof.
    """

    @abstractmethod
    async def repaired(self, event: StrandedAuthorityRepairedAuditEventDTO) -> None: ...
