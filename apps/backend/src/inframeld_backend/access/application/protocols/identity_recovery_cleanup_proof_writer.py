from abc import abstractmethod
from datetime import datetime
from typing import Protocol

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_proof_dto import (
    IdentityRecoveryCleanupProofDTO,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class IdentityRecoveryCleanupProofWriter(Protocol):
    """Persist checked proof and completion without committing or granting access.

    Apply coverage under the original identity and required organization locks.
    Preserve immutable provenance and end covered dispatch without recalling calls.
    """

    @abstractmethod
    async def apply_to_covered(
        self,
        source: IdentityRecoveryCleanupProofDTO,
        target: IdentityRecoveryAdmissionDTO,
        *,
        at: datetime,
    ) -> None: ...

    @abstractmethod
    async def record_checked(
        self, operation_id: OperationId, *, at: datetime, released: bool
    ) -> None: ...

    @abstractmethod
    async def defer(self, operation_id: OperationId, *, until: datetime) -> None: ...

    @abstractmethod
    async def mark_propagated(self, operation_id: OperationId) -> None: ...
