from dataclasses import dataclass

from inframeld_backend.access.application.dtos.created_access_group_dto import (
    CreatedAccessGroupDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True)
class AccessGroupCreationResultDTO:
    group: CreatedAccessGroupDTO
    operation: CompletedSynchronousOperationDTO
