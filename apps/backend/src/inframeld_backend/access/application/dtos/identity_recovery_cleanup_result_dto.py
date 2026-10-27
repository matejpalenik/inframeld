from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class IdentityRecoveryCleanupResultDTO:
    """Report this flow's committed checklist, not permission to use the product.

    Release concerns this flow only. Other recovery blocks and current account,
    credential and permission checks still apply on every product request.
    """

    operation_id: OperationId
    kratos_cleanup_state: IdentityRecoveryCleanupState
    hydra_cleanup_state: IdentityRecoveryCleanupState
    released_at: datetime | None
    has_other_pending_recovery: bool
