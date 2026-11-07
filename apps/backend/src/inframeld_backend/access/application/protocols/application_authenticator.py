from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)


class ApplicationAuthenticator(Protocol):
    @abstractmethod
    async def authenticate(self, credential: ApplicationKeyCredential) -> AccessContextDTO:
        """Verify the key, separately admit its current account and retain no secret.

        Invalid keys raise AuthenticationRequiredError. Current local ineligibility
        raises AccessDeniedError. Required dependency uncertainty raises
        DependencyUnavailableError. Do not provision accounts or cache permissions.
        """
        ...
