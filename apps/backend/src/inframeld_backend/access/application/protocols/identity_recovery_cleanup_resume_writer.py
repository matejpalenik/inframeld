from abc import abstractmethod
from datetime import datetime
from typing import Protocol

from inframeld_backend.access.application.dtos.identity_recovery_cleanup_work_dto import (
    IdentityRecoveryCleanupWorkDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_maintenance_receipt_dto import (
    IdentityRecoveryMaintenanceReceiptDTO,
)


class IdentityRecoveryCleanupResumeWriter(Protocol):
    """Save checked host authorization without committing or dispatching provider work."""

    @abstractmethod
    async def record(self, receipt: IdentityRecoveryMaintenanceReceiptDTO) -> bool:
        """Insert the complete immutable audit/replay receipt before other effects.

        Return False if another request owns this installation/request key.
        The caller must read and compare that receipt before changing runs.
        """
        ...

    @abstractmethod
    async def authorize_run(self, receipt: IdentityRecoveryMaintenanceReceiptDTO) -> None:
        """Create exactly the run already described by this transaction's receipt."""
        ...

    @abstractmethod
    async def settle(
        self, work: IdentityRecoveryCleanupWorkDTO, *, at: datetime, terminal_reason: str
    ) -> None:
        """End the checked old run and fence ownership, retaining dispatched uncertainty."""
        ...

    @abstractmethod
    async def save_complete_proof(
        self, work: IdentityRecoveryCleanupWorkDTO, *, at: datetime
    ) -> None:
        """Retain existing confirmations for normal local reconciliation, without provider work."""
        ...
