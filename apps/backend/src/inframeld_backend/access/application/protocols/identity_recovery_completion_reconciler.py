from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.identity_recovery_cleanup_result_dto import (
    IdentityRecoveryCleanupResultDTO,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class IdentityRecoveryCompletionReconciler(Protocol):
    """Finish original checklists from durable proof, never caller-supplied outcomes."""

    @abstractmethod
    async def reconcile_proof(
        self, *, operation_id: OperationId, covering_operation_id: OperationId | None = None
    ) -> IdentityRecoveryCleanupResultDTO: ...
