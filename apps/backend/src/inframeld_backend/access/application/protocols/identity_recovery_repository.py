from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.domain.entities.identity_recovery import IdentityRecovery
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class IdentityRecoveryRepository(Protocol):
    """Load and save the cleanup checklist for an already admitted recovery.

    The caller owns the transaction. Provider calls belong outside it, and
    loading a checklist does not authenticate a callback or authorize release.
    """

    @abstractmethod
    async def get(
        self,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
        flow_id: IdentityRecoveryFlowId,
    ) -> IdentityRecovery:
        """Load one original flow in its trusted installation and provider scope.

        Repeated loads in this transaction return the same instance, including
        its unsaved changes. A missing recovery is never created here.

        Args:
            installation_id: Installation established by trusted configuration.
            authority: Provider established by trusted configuration.
            flow_id: Original admitted flow, not a later password-settings flow.

        Raises:
            ResourceNotFoundError: No admission exists in this exact scope.
            RuntimeError: No active transaction exists, or the repository belongs
                to another transaction or has failed during save.
        """
        ...

    @abstractmethod
    async def save(self, recovery: IdentityRecovery) -> None:
        """Save cleanup progress or release state without committing.

        Use the instance loaded by this repository in the same transaction.
        Unchanged state causes no writes.

        Before release, the application must check current eligibility and
        other pending recoveries under the required coordination locks.

        If saving fails, roll back and discard this repository.

        Raises:
            ConflictError: The stored recovery changed or disappeared.
                Reload in a new transaction before proceeding.
            RuntimeError: The instance was not loaded here, its identity
                binding changed, or the transaction is unusable.
        """
        ...
