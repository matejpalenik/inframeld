from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.stranded_authority_repair_facts_dto import (
    StrandedAuthorityRepairFactsDTO,
)
from inframeld_backend.access.application.dtos.stranded_authority_repair_receipt_dto import (
    StrandedAuthorityRepairReceiptDTO,
)


class StrandedAuthorityRepairWriter(Protocol):
    """Save only checked responsibility repair in the same transaction as its receipt and audit."""

    @abstractmethod
    async def record(self, receipt: StrandedAuthorityRepairReceiptDTO) -> bool:
        """Claim the common request key or return false for a concurrent committed winner."""
        ...

    @abstractmethod
    async def assign(
        self, *, facts: StrandedAuthorityRepairFactsDTO, receipt: StrandedAuthorityRepairReceiptDTO
    ) -> None: ...
