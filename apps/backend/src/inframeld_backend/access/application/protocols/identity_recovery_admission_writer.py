from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)


class IdentityRecoveryAdmissionWriter(Protocol):
    """Reserve recovery admission within the caller's transaction.

    Use trusted installation/provider configuration to scope the original flow.
    A new admission saves its cleanup obligation and product block atomically.
    An existing admission returns its original binding without restarting cleanup,
    replacing its operation, or recreating a completed block. Do not commit here.
    """

    @abstractmethod
    async def reserve(self, event: IdentityRecoveryEventDTO) -> IdentityRecoveryAdmissionDTO:
        """Return the stored admission so the service can check its original binding."""
        ...
