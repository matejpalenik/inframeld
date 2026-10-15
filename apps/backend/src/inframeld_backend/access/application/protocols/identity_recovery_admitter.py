from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class IdentityRecoveryAdmitter(Protocol):
    """Accept trusted recovery evidence without performing provider cleanup."""

    @abstractmethod
    async def admit(self, event: IdentityRecoveryEventDTO) -> OperationId:
        """Return the original operation or reject a conflicting flow binding.

        The caller must authenticate and validate the provider evidence first,
        then commit admission before acknowledging the callback.

        This result does not confirm either provider's cleanup.

        Raises:
            ConflictError: The flow is already bound to a different identity or event."""
        ...
