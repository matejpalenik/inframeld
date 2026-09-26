"""Adapt a browser request to the human-authentication application operation."""

from starlette.requests import Request

from inframeld_backend.access.application.access_context import AccessContext
from inframeld_backend.access.application.authentication.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.authentication.human_session_authenticator import (
    HumanSessionAuthenticator,
)

_SESSION_COOKIE_NAME = "ory_kratos_session"


class HumanSessionDependency:
    """Extract the browser credential and invoke authentication for a protected FastAPI route."""

    def __init__(self, authenticator: HumanSessionAuthenticator) -> None:
        """Bind this dependency to the application authentication operation."""
        self._authenticator = authenticator

    async def __call__(self, request: Request) -> AccessContext:
        """Pass absent credentials to the service so deployment and admission rules stay together."""
        raw_cookie = request.cookies.get(_SESSION_COOKIE_NAME)
        credential = BrowserSessionCredential(raw_cookie) if raw_cookie else None
        return await self._authenticator.authenticate(credential)
