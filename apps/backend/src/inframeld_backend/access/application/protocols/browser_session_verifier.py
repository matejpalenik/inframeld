from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)


class BrowserSessionVerifier(Protocol):
    """Establish external identity before the application considers local access."""

    @abstractmethod
    async def verify(self, credential: BrowserSessionCredential) -> VerifiedHumanIdentityDTO | None:
        """Verify the untrusted credential with the identity provider.

        Return its verified source and subject, or None for a rejected session.
        Raise `DependencyUnavailableError` for unavailable or malformed provider
        responses. Verification establishes identity without granting local access."""
        ...
