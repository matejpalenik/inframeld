"""Fail closed when deployment configuration provides no human identity verifier."""

from typing import override

from inframeld_backend.access.application.access_context import AccessContext
from inframeld_backend.access.application.authentication.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.authentication.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.shared.application.errors import DependencyUnavailableError


class UnavailableHumanSessionAuthenticationService(HumanSessionAuthenticator):
    """Reject protected operations when human authentication is not configured."""

    @override
    async def authenticate(self, credential: BrowserSessionCredential | None) -> AccessContext:
        """Report unavailable authentication consistently when no provider has been configured."""
        raise DependencyUnavailableError()
