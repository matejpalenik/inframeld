from dataclasses import dataclass

from inframeld_backend.access.application.dtos.project_upload_default_dto import (
    ProjectUploadDefaultDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True)
class ProjectUploadDefaultChangeResultDTO:
    """Expose only the original resulting audience, never its private before snapshot."""

    default: ProjectUploadDefaultDTO
    operation: CompletedSynchronousOperationDTO
