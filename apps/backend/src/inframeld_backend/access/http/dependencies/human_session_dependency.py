"""Select one human credential family before invoking authentication."""

import re
from typing import Annotated

from fastapi import Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from starlette.exceptions import HTTPException
from starlette.requests import Request

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.http.validation.invalid_authentication_request_error import (
    InvalidAuthenticationRequestError,
)

_SESSION_COOKIE_NAME = "ory_kratos_session"
_BEARER_CHALLENGE = 'Bearer realm="inframeld"'
_INVALID_TOKEN_CHALLENGE = f'{_BEARER_CHALLENGE}, error="invalid_token"'
_INVALID_REQUEST_CHALLENGE = f'{_BEARER_CHALLENGE}, error="invalid_request"'
_AUTHORIZATION_SCHEME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
_BEARER_AUTHORIZATION = re.compile(r"(?i:Bearer) +([A-Za-z0-9._~+/-]+=*)")

_COOKIE_SECURITY = APIKeyCookie(
    name=_SESSION_COOKIE_NAME,
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


def _invalid_request(authorizations: list[str]) -> InvalidAuthenticationRequestError:
    """Attach a constant Bearer challenge only when that scheme was attempted."""
    for value in authorizations:
        parts = value.split(None, 1)
        if parts and parts[0].casefold() == "bearer":
            return InvalidAuthenticationRequestError(
                headers={"WWW-Authenticate": _INVALID_REQUEST_CHALLENGE}
            )
    return InvalidAuthenticationRequestError()


def _unauthorized(challenge: str) -> HTTPException:
    return HTTPException(status_code=401, headers={"WWW-Authenticate": challenge})


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
        authorizations = request.headers.getlist("Authorization")
        cookies = request.cookies

        if len(authorizations) > 1 or (authorizations and _SESSION_COOKIE_NAME in cookies):
            raise _invalid_request(authorizations)

        if not authorizations:
            raw_cookie = cookies.get(_SESSION_COOKIE_NAME)
            if not raw_cookie:
                raise _unauthorized(_BEARER_CHALLENGE)

            access = await self._authenticator.authenticate(BrowserSessionCredential(raw_cookie))
            self._csrf(request)
            return access

        raw_header = authorizations[0].strip(" \t")
        scheme, separator, parameters = raw_header.partition(" ")
        if (
            not separator
            or not parameters.strip(" ")
            or _AUTHORIZATION_SCHEME.fullmatch(scheme) is None
        ):
            raise _invalid_request(authorizations)

        if scheme.casefold() != "bearer":
            raise _unauthorized(_BEARER_CHALLENGE)

        match = _BEARER_AUTHORIZATION.fullmatch(raw_header)
        if match is None:
            raise _invalid_request(authorizations)

        token = match.group(1)
        if token.startswith("ifm_app_"):
            raise _unauthorized(_INVALID_TOKEN_CHALLENGE)

        try:
            credential = HumanAccessTokenCredential(token)
        except ValueError:
            raise _unauthorized(_INVALID_TOKEN_CHALLENGE) from None

        if self._access_token_authenticator is None:
            raise DependencyUnavailableError()

        try:
            return await self._access_token_authenticator.authenticate(credential)
        except AuthenticationRequiredError:
            raise _unauthorized(_INVALID_TOKEN_CHALLENGE) from None
