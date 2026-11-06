from dataclasses import dataclass

from inframeld_backend.access.application.dtos.deleted_access_group_dto import (
    DeletedAccessGroupDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True)
class AccessGroupDeletionResultDTO:
    group: DeletedAccessGroupDTO
    operation: CompletedSynchronousOperationDTO
