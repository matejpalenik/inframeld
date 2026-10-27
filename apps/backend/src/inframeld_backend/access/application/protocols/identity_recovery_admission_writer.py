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

    Use an active READ COMMITTED transaction and trusted installation/provider
    configuration. Acquire identity coordination before organization locks and
    read current facts afterward. The caller bounds the complete database stage.
    Admission does not require or create a local principal, membership, or grant.

    A new admission atomically saves its block, advances the credential version
    once and links older unfinished recoveries for the same verified identity.
    A repeat never expands those links.

    An existing admission returns its original binding without restarting cleanup,
    replacing its operation, or recreating a completed block. The caller commits
    or rolls back, releasing identity coordination with the transaction.
    """

    @abstractmethod
    async def reserve(self, event: IdentityRecoveryEventDTO) -> IdentityRecoveryAdmissionDTO:
        """Return the stored admission so the service can check its original binding."""
        ...
