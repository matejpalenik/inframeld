from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.set_project_upload_default_command import (
    SetProjectUploadDefaultCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_upload_default_change_result_dto import (
    ProjectUploadDefaultChangeResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class ProjectUploadDefaultChanger(Protocol):
    @abstractmethod
    async def set(
        self,
        *,
        access: AccessContextDTO,
        command: SetProjectUploadDefaultCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectUploadDefaultChangeResultDTO:
        """Authorize current saved/proposed groups before recovering or replacing the default.

        Recover the immutable original before fresh revision checks. A fresh no-op
        still requires the reviewed revision and retains its own safe original.
        """
        ...
