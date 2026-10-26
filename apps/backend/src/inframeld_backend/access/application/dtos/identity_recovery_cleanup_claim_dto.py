from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class IdentityRecoveryCleanupClaimDTO:
    """Identify one consumed attempt, not permission to ignore current ownership."""

    operation_id: OperationId
    run_id: UUID
    attempt_id: UUID
    worker_id: UUID
    token: UUID
    lease_expires_at: datetime
