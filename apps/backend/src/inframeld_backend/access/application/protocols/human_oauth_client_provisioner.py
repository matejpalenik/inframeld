from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.enums.human_oauth_client_provisioning_outcome import (
    HumanOAuthClientProvisioningOutcome,
)
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience


class HumanOAuthClientProvisioner(Protocol):
    """Configure the installation's official public CLI client through private administration.

    Host installation tooling supplies authority and the trusted API audience.
    Ordinary API startup and product credentials do not invoke this operation.
    """

    @abstractmethod
    async def ensure_client(
        self, *, api_audience: HumanAPIAudience, timeout_seconds: float
    ) -> HumanOAuthClientProvisioningOutcome:
        """Create or reconcile the fixed client, preserving existing login chains.

        Verify the resulting profile before returning. Matching configuration
        performs no write. Do not hold an application database transaction.

        Raises:
            OAuthClientProvisioningRejectedError: Configuration was explicitly rejected.
            OAuthClientProvisioningUncertainError: A write may have applied without verification.
            DependencyUnavailableError: Required provider state could not be read.
            ValueError: The deadline is not finite and positive.

        Stopping before write admission prevents mutation. Once admitted, a write
        may still be dispatched or complete after timeout or cancellation.
        Cancellation propagates, and timeout then reports an uncertain outcome.
        """
        ...
