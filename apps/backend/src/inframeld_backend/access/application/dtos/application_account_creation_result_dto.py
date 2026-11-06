from dataclasses import dataclass

from inframeld_backend.access.application.dtos.created_application_account_dto import (
    CreatedApplicationAccountDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True)
class ApplicationAccountCreationResultDTO:
    account: CreatedApplicationAccountDTO
    operation: CompletedSynchronousOperationDTO
