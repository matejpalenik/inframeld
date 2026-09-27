from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)


class HumanSessionAuthenticator(Protocol):
    """Admit a verified browser user as an active local human caller."""

    @abstractmethod
    async def authenticate(self, credential: BrowserSessionCredential | None) -> AccessContextDTO:
        """Authenticate a browser credential and admit its active local human.

        Return an `AccessContextDTO` after provider verification and local admission.
        Raise `AuthenticationRequiredError` for missing/rejected credentials,
        `AccessDeniedError` for an absent or ineligible local principal, and
        `DependencyUnavailableError` when session verification is unavailable.
        Implementations perform I/O through ports without exposing transport types."""
        ...
