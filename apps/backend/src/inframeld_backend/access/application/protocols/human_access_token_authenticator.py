from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)


class HumanAccessTokenAuthenticator(Protocol):
    """Resolve a human token to its currently admitted local caller."""

    @abstractmethod
    async def authenticate(self, credential: HumanAccessTokenCredential | None) -> AccessContextDTO:
        """Verify providers before reading current local account state.

        Raise `AuthenticationRequiredError` for missing or rejected credentials.

        Raise `AccessDeniedError` for absent or ineligible local admission.

        Raise `DependencyUnavailableError` when required verification cannot be confirmed.

        Return principal identity only - authorization remains separate."""
        ...
