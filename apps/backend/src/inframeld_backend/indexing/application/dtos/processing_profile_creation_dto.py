from dataclasses import dataclass
from typing import Literal

from inframeld_backend.indexing.application.dtos.processing_profile_dto import ProcessingProfileDTO
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessingProfileCreationDTO:
    profile: ProcessingProfileDTO
    operation: CompletedSynchronousOperationDTO
    project_access_revision: int
    initial_actions: tuple[ProcessingProfileAction, ...]
    can_grant: Literal[True]
