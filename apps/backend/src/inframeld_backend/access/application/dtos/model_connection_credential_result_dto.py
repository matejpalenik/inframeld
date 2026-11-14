from dataclasses import dataclass

from inframeld_backend.access.application.dtos.model_connection_credential_dto import (
    ModelConnectionCredentialDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True)
class ModelConnectionCredentialResultDTO:
    credential: ModelConnectionCredentialDTO
    changed: bool
    operation: CompletedSynchronousOperationDTO
