from dataclasses import dataclass
from typing import Literal

from inframeld_backend.access.application.dtos.processing_profile_grant_target_dto import (
    ProcessingProfileGrantTargetDTO,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True)
class ProcessingProfileGrantResultDTO:
    target: ProcessingProfileGrantTargetDTO
    recipient_id: PrincipalId
    action: ProcessingProfileAction
    can_grant: bool | None
    access_revision: int
    changed: bool
    status_code: Literal[200, 201]
    operation: CompletedSynchronousOperationDTO
