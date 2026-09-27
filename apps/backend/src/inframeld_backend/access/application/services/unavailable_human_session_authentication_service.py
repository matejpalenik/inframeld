"""Fail closed when deployment configuration provides no human identity verifier."""

from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)


class UnavailableHumanSessionAuthenticationService(HumanSessionAuthenticator):
    """Reject protected operations when human authentication is not configured."""

    @override
    async def authenticate(self, credential: BrowserSessionCredential | None) -> AccessContextDTO:
        raise DependencyUnavailableError()
