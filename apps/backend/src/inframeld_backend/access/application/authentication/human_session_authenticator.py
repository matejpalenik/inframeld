"""Define the HumanSessionAuthenticator application boundary."""

from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.access_context import AccessContext
from inframeld_backend.access.application.authentication.browser_session_credential import (
    BrowserSessionCredential,
)


class HumanSessionAuthenticator(Protocol):
    """Authenticate a browser credential and admit its active local human."""

    @abstractmethod
    async def authenticate(self, credential: BrowserSessionCredential | None) -> AccessContext:
        """Authenticate a browser credential and admit its active local human.

        Return an AccessContext after provider verification and local admission.
        Raise AuthenticationRequiredError for missing/rejected credentials,
        AccessDeniedError for an absent or ineligible local principal, and
        DependencyUnavailableError when session verification is unavailable.
        Implementations perform I/O through ports without exposing transport types."""
        ...
