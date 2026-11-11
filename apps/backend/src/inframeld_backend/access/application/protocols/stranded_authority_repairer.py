from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.repair_stranded_authority_command import (
    RepairStrandedAuthorityCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.stranded_authority_repair_result_dto import (
    StrandedAuthorityRepairResultDTO,
)


class StrandedAuthorityRepairer(Protocol):
    """Repair one reviewed stranded responsibility through host-authorized maintenance only.

    The CLI verifies recipient proof before opening the operation session. This capability
    rechecks its current local binding/generation and eligibility before replay or mutation.
    Host execution supplies authority. No product endpoint may expose this operation.
    """

    @abstractmethod
    async def repair(
        self, *, access: AccessContextDTO, command: RepairStrandedAuthorityCommand
    ) -> StrandedAuthorityRepairResultDTO: ...
