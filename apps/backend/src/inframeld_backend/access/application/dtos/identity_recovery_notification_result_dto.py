from dataclasses import dataclass

from inframeld_backend.access.application.enums.identity_recovery_evidence_type import (
    IdentityRecoveryEvidenceType,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class IdentityRecoveryNotificationResultDTO:
    operation_id: OperationId
    event_type: IdentityRecoveryEvidenceType
