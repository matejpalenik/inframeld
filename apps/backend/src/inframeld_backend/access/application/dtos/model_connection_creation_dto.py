from dataclasses import dataclass

from inframeld_backend.access.application.dtos.model_connection_dto import ModelConnectionDTO
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True)
class ModelConnectionCreationDTO:
    connection: ModelConnectionDTO
    operation: CompletedSynchronousOperationDTO
    project_access_revision: int
    initial_actions: tuple[ModelConnectionAction, ...]
