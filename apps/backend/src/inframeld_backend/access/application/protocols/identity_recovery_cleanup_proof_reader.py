from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_proof_dto import (
    IdentityRecoveryCleanupProofDTO,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class IdentityRecoveryCleanupProofReader(Protocol):
    """Observe saved proof and explicit coverage in the caller's transaction."""

    @abstractmethod
    async def pending_operations(self, *, limit: int) -> tuple[OperationId, ...]: ...

    @abstractmethod
    async def read_admission(self, operation_id: OperationId) -> IdentityRecoveryAdmissionDTO: ...

    @abstractmethod
    async def read_proof(
        self, operation_id: OperationId
    ) -> IdentityRecoveryCleanupProofDTO | None: ...

    @abstractmethod
    async def linked_older(self, source: OperationId, *, limit: int) -> tuple[OperationId, ...]: ...

    @abstractmethod
    async def is_linked(self, source: OperationId, target: OperationId) -> bool: ...
