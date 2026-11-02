from dataclasses import dataclass

from inframeld_backend.access.application.dtos.created_project_dto import CreatedProjectDTO
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True)
class ProjectCreationResultDTO:
    project: CreatedProjectDTO
    operation: CompletedSynchronousOperationDTO
