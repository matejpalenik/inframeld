"""Define the BrowserSessionVerifier application boundary."""

from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.authentication.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.authentication.verified_human_identity import (
    VerifiedHumanIdentity,
)


class BrowserSessionVerifier(Protocol):
    """Verify the untrusted credential with the identity provider."""

    @abstractmethod
    async def verify(self, credential: BrowserSessionCredential) -> VerifiedHumanIdentity | None:
        """Verify the untrusted credential with the identity provider.

        Return its verified source and subject, or None for a rejected session.
        Raise `DependencyUnavailableError` for unavailable or malformed provider
        responses. Verification establishes identity without granting local access."""
        ...
