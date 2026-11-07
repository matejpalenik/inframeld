from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.application_authenticator import (
    ApplicationAuthenticator,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)


class MockApplicationAuthenticator(ApplicationAuthenticator):
    """Control application authentication without pretending to verify a persisted key."""

    def __init__(self, access: AccessContextDTO, *, failure: Exception | None = None) -> None:
        self.access = access
        self.calls = 0
        self.failure = failure

    @override
    async def authenticate(self, credential: ApplicationKeyCredential) -> AccessContextDTO:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.access
