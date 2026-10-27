from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)


class HumanAccessTokenVerifier(Protocol):
    """Verify a human access token before checking current Kratos eligibility"""

    @abstractmethod
    async def verify(
        self, credential: HumanAccessTokenCredential, *, timeout_seconds: float
    ) -> HumanOAuthCredentialBindingDTO | None:
        """Return the verified identity and stored credential binding.

        Require current access token validity and the configured issuer, client,
        API audience, scopes and valid version metadata. Current local version equality
        remains the authentication service's responsibility.

        Return `None` for rejected credentials.

        Raise `DependencyUnavailableError` for unavailable or malformed provider verification.

        Bound provider I/O by `timeout_seconds` and cache no success.

        This result does not establish current Kratos eligibility or local admission.
        """
        ...
