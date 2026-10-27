from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_resume_facts_dto import (
    IdentityRecoveryCleanupResumeFactsDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_maintenance_receipt_dto import (
    IdentityRecoveryMaintenanceReceiptDTO,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class IdentityRecoveryCleanupResumeFactsReader(Protocol):
    """Read maintenance receipts and original recovery observations in the caller transaction.

    Current facts follow identity and organization coordination. Loading the
    original admission only identifies which trusted identity needs that lock.
    """

    @abstractmethod
    async def installation(self) -> InstallationId | None: ...

    @abstractmethod
    async def receipt(
        self, *, installation_id: InstallationId, operation_id: OperationId
    ) -> IdentityRecoveryMaintenanceReceiptDTO | None: ...

    @abstractmethod
    async def original(
        self, *, installation_id: InstallationId, operation_id: OperationId
    ) -> IdentityRecoveryAdmissionDTO | None: ...

    @abstractmethod
    async def read(
        self, *, installation_id: InstallationId, admission: IdentityRecoveryAdmissionDTO
    ) -> IdentityRecoveryCleanupResumeFactsDTO: ...
