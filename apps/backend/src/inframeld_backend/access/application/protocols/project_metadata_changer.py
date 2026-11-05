from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.update_project_metadata_command import (
    UpdateProjectMetadataCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_metadata_change_result_dto import (
    ProjectMetadataChangeResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)


class ProjectMetadataChanger(Protocol):
    """Atomically change metadata, reserve its exact name, audit and retain its original outcome.

    Recheck current authority before replay. Omitted replacements preserve legacy labels.
    """

    @abstractmethod
    async def update(
        self,
        *,
        access: AccessContextDTO,
        command: UpdateProjectMetadataCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectMetadataChangeResultDTO: ...
