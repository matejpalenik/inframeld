from dataclasses import dataclass

from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class IdentityRecoveryAdmissionDTO:
    """Carry the original stored binding and operation, including after cleanup completes."""

    event: IdentityRecoveryEventDTO
    operation_id: OperationId
