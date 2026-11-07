from typing import Annotated

from fastapi import Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from starlette.requests import Request

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.application_authenticator import (
    ApplicationAuthenticator,
)
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
    name="ory_kratos_session", scheme_name="KratosSession", auto_error=False
)
_BEARER_SECURITY = HTTPBearer(
    scheme_name="ProductBearer",
    description="Opaque human access token or complete Inframeld application key.",
    auto_error=False,
)


class ProductAccessDependency:
    """Authenticate one product credential family without weakening operation-kind rules."""

    def __init__(
        self,
        authenticator: HumanSessionAuthenticator,
        csrf: CSRFProtectionDependency,
        *,
        access_token_authenticator: HumanAccessTokenAuthenticator | None = None,
        application_authenticator: ApplicationAuthenticator,
    ) -> None:
        self._authenticator = authenticator
        self._csrf = csrf
        self._access_token_authenticator = access_token_authenticator
        self._application_authenticator = application_authenticator

    async def __call__(
        self,
        request: Request,
        _cookie_schema: Annotated[str | None, Security(_COOKIE_SECURITY)],
        _bearer_schema: Annotated[HTTPAuthorizationCredentials | None, Security(_BEARER_SECURITY)],
    ) -> AccessContextDTO:
        credential = IncomingCredentialMapper.select(
            authorization_headers=request.headers.getlist("Authorization"), cookies=request.cookies
        )
        if credential is None:
            raise IncomingCredentialMapper.unauthorized()
        if isinstance(credential, BrowserSessionCredential):
            access = await self._authenticator.authenticate(credential)
            self._csrf(request)
            return access

        try:
            if isinstance(credential, ApplicationKeyCredential):
                return await self._application_authenticator.authenticate(credential)
            if self._access_token_authenticator is None:
                raise DependencyUnavailableError()
            return await self._access_token_authenticator.authenticate(credential)
        except AuthenticationRequiredError:
            raise IncomingCredentialMapper.unauthorized(invalid_token=True) from None
