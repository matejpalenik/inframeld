from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.repair_project_metadata_authority_command import (
    RepairProjectMetadataAuthorityCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_metadata_repair_result_dto import (
    ProjectMetadataRepairResultDTO,
)


class ProjectMetadataRepairer(Protocol):
    """Repair one reviewed stranded metadata grant through host-authorized maintenance only.

    The CLI verifies recipient proof before opening the operation session. This capability
    rechecks its current local binding/generation and eligibility before replay or mutation.
    Host execution supplies authority. No product endpoint may expose this operation.
    """

    @abstractmethod
    async def repair(
        self, *, access: AccessContextDTO, command: RepairProjectMetadataAuthorityCommand
    ) -> ProjectMetadataRepairResultDTO: ...
