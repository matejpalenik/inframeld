from dataclasses import dataclass, field

from inframeld_backend.access.application.dtos.application_key_issuance_record_dto import (
    ApplicationKeyIssuanceRecordDTO,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True)
class ApplicationKeyIssueResultDTO:
    """Carry plaintext only for the confirmed original first delivery."""

    original: ApplicationKeyIssuanceRecordDTO
    operation: CompletedSynchronousOperationDTO
    credential: ApplicationKeyCredential | None = field(repr=False)
