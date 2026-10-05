from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)


class HumanAccessTokenVerifier(Protocol):
    """Verify a human access token before checking current Kratos eligibility"""

    @abstractmethod
    async def verify(
        self, credential: HumanAccessTokenCredential, *, timeout_seconds: float
    ) -> VerifiedHumanIdentityDTO | None:
        """Return the trusted Kratos authority / subject after token verification.

        Require current access token validity and the configured issuer, client,
        API audience and scopes.

        Return `None` for rejected credentials.

        Raise `DependencyUnavailableError` for unavailable or malformed provider verification.

        Bound provider I/O by `timeout_seconds` and cache no success.

        This result does not establish current Kratos eligibility or local admission.
        """
        ...
