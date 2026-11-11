from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.repair_stranded_authority_command import (
    RepairStrandedAuthorityCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.stranded_authority_repair_facts_dto import (
    StrandedAuthorityRepairFactsDTO,
)
from inframeld_backend.access.application.dtos.stranded_authority_repair_receipt_dto import (
    StrandedAuthorityRepairReceiptDTO,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class StrandedAuthorityRepairFactsReader(Protocol):
    """Observe fresh recipient facts after identity, Organization and Project coordination.

    The caller owns the transaction. Receipt reads preserve the common host request namespace
    and reject another mode before decoding mode-specific fields.
    """

    @abstractmethod
    async def read(
        self, *, access: AccessContextDTO, command: RepairStrandedAuthorityCommand
    ) -> StrandedAuthorityRepairFactsDTO | None: ...

    @abstractmethod
    async def receipt(
        self, *, installation_id: InstallationId, operation_id: OperationId
    ) -> StrandedAuthorityRepairReceiptDTO | None: ...
