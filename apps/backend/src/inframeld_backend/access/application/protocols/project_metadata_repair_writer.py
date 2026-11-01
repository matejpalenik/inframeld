from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.project_metadata_repair_facts_dto import (
    ProjectMetadataRepairFactsDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_repair_receipt_dto import (
    ProjectMetadataRepairReceiptDTO,
)


class ProjectMetadataRepairWriter(Protocol):
    """Save only checked metadata repair in the same transaction as its receipt and audit."""

    @abstractmethod
    async def record(self, receipt: ProjectMetadataRepairReceiptDTO) -> bool:
        """Claim the common request key or return false for a concurrent committed winner."""
        ...

    @abstractmethod
    async def assign(
        self, *, facts: ProjectMetadataRepairFactsDTO, receipt: ProjectMetadataRepairReceiptDTO
    ) -> None: ...
