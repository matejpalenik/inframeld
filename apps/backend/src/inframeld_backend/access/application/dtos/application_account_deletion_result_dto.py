from dataclasses import dataclass

from inframeld_backend.access.application.dtos.application_account_deletion_record_dto import (
    ApplicationAccountDeletionRecordDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True)
class ApplicationAccountDeletionResultDTO:
    original: ApplicationAccountDeletionRecordDTO
    operation: CompletedSynchronousOperationDTO
