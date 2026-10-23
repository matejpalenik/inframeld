from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.identity_recovery_completion_facts_dto import (
    IdentityRecoveryCompletionFactsDTO,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class IdentityRecoveryCompletionFactsReader(Protocol):
    """Read the existing recovery binding and current release facts without provisioning.

    Use the caller's active transaction. For a linked human, hold the existing
    exclusive organization lock through commit or rollback before reading facts.
    """

    @abstractmethod
    async def read(
        self,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
        flow_id: IdentityRecoveryFlowId,
    ) -> IdentityRecoveryCompletionFactsDTO:
        """Read one original flow in its configured installation and provider scope.

        Raises:
            ResourceNotFoundError: This flow has no admission in the exact scope.
            DependencyUnavailableError: Installation metadata is unavailable or
                mismatched, or the database deadline expires.
            RuntimeError: No active caller transaction exists or stored identity
                relationships are inconsistent.
        """
        ...
