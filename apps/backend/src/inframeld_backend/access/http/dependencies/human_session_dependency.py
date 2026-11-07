"""Select one human credential family before invoking authentication."""

from typing import Annotated

from fastapi import Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from starlette.requests import Request

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.mappers.incoming_credential_mapper import (
    IncomingCredentialMapper,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
    DependencyUnavailableError,
)

_COOKIE_SECURITY = APIKeyCookie(
    name="ory_kratos_session",
    scheme_name="KratosSession",
    description=(
        "Kratos browser session. Cookie-authenticated writes also require "
        "a trusted Origin and X-Inframeld-CSRF: 1."
    ),
    auto_error=False,
)
_BEARER_SECURITY = HTTPBearer(
    scheme_name="HumanBearer",
    description="Opaque human Hydra access token. Application keys do not authenticate a human.",
    auto_error=False,
)


class HumanSessionDependency:
    """Authenticate a browser or human bearer request without credential fallback."""

    def __init__(
        self,
        authenticator: HumanSessionAuthenticator,
        csrf: CSRFProtectionDependency,
        *,
        access_token_authenticator: HumanAccessTokenAuthenticator | None = None,
    ) -> None:
        self._authenticator = authenticator
        self._csrf = csrf
        self._access_token_authenticator = access_token_authenticator

    async def __call__(
        self,
        request: Request,
        _cookie_schema: Annotated[str | None, Security(_COOKIE_SECURITY)],
        _bearer_schema: Annotated[HTTPAuthorizationCredentials | None, Security(_BEARER_SECURITY)],
    ) -> AccessContextDTO:
        """Check raw headers before provider I/O; apply CSRF only on the cookie path.

        Optional Security dependencies declare OpenAPI alternatives. Their parsed
        values cannot establish an unambiguous credential, so dispatch uses the
        original request and checks duplicates and competing mechanisms itself.
        """
        credential = IncomingCredentialMapper.select(
            authorization_headers=request.headers.getlist("Authorization"), cookies=request.cookies
        )
        if credential is None:
            raise IncomingCredentialMapper.unauthorized()
        if isinstance(credential, ApplicationKeyCredential):
            raise IncomingCredentialMapper.unauthorized(invalid_token=True)
        if isinstance(credential, BrowserSessionCredential):
            access = await self._authenticator.authenticate(credential)
            self._csrf(request)
            return access

        if self._access_token_authenticator is None:
            raise DependencyUnavailableError()
        try:
            return await self._access_token_authenticator.authenticate(credential)
        except AuthenticationRequiredError:
            raise IncomingCredentialMapper.unauthorized(invalid_token=True) from None
