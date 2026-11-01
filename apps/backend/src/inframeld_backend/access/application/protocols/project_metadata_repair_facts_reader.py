from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.repair_project_metadata_authority_command import (
    RepairProjectMetadataAuthorityCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_metadata_repair_facts_dto import (
    ProjectMetadataRepairFactsDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_repair_receipt_dto import (
    ProjectMetadataRepairReceiptDTO,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class ProjectMetadataRepairFactsReader(Protocol):
    """Observe fresh recipient facts after identity, Organization and Project coordination.

    The caller owns the transaction. Receipt reads preserve the common host request namespace
    and reject another mode before decoding mode-specific fields.
    """

    @abstractmethod
    async def read(
        self, *, access: AccessContextDTO, command: RepairProjectMetadataAuthorityCommand
    ) -> ProjectMetadataRepairFactsDTO | None: ...

    @abstractmethod
    async def receipt(
        self, *, installation_id: InstallationId, operation_id: OperationId
    ) -> ProjectMetadataRepairReceiptDTO | None: ...
