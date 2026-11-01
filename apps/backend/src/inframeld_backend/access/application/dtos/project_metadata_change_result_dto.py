from dataclasses import dataclass

from inframeld_backend.access.application.dtos.project_metadata_dto import ProjectMetadataDTO
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True)
class ProjectMetadataChangeResultDTO:
    metadata: ProjectMetadataDTO
    operation: CompletedSynchronousOperationDTO
