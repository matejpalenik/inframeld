from dataclasses import dataclass

from inframeld_backend.access.application.dtos.application_key_revocation_record_dto import (
    ApplicationKeyRevocationRecordDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True)
class ApplicationKeyRevocationResultDTO:
    original: ApplicationKeyRevocationRecordDTO
    operation: CompletedSynchronousOperationDTO
