from datetime import datetime
from typing import override

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_proof_dto import (
    IdentityRecoveryCleanupProofDTO,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_proof_reader import (
    IdentityRecoveryCleanupProofReader,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_proof_writer import (
    IdentityRecoveryCleanupProofWriter,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class MockIdentityRecoveryCleanupProofs(
    IdentityRecoveryCleanupProofReader, IdentityRecoveryCleanupProofWriter
):
    def __init__(self, admission: IdentityRecoveryAdmissionDTO) -> None:
        self.admission = admission
        self.proof: IdentityRecoveryCleanupProofDTO | None = None
        self.checked: list[tuple[OperationId, bool]] = []
        self.linked = False

    @override
    async def pending_operations(self, *, limit: int) -> tuple[OperationId, ...]:
        return ()

    @override
    async def read_admission(self, operation_id: OperationId) -> IdentityRecoveryAdmissionDTO:
        return self.admission

    @override
    async def read_proof(self, operation_id: OperationId) -> IdentityRecoveryCleanupProofDTO | None:
        return self.proof

    @override
    async def linked_older(self, source: OperationId, *, limit: int) -> tuple[OperationId, ...]:
        return ()

    @override
    async def is_linked(self, source: OperationId, target: OperationId) -> bool:
        return self.linked

    @override
    async def apply_to_covered(
        self,
        source: IdentityRecoveryCleanupProofDTO,
        target: IdentityRecoveryAdmissionDTO,
        *,
        at: datetime,
    ) -> None:
        pass

    @override
    async def record_checked(
        self, operation_id: OperationId, *, at: datetime, released: bool
    ) -> None:
        self.checked.append((operation_id, released))

    @override
    async def defer(self, operation_id: OperationId, *, until: datetime) -> None:
        pass

    @override
    async def mark_propagated(self, operation_id: OperationId) -> None:
        pass
