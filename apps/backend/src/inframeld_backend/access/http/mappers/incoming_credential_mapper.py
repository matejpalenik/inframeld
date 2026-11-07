import re
from collections.abc import Mapping, Sequence

from starlette.exceptions import HTTPException

from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.http.types.incoming_credential import IncomingCredential
from inframeld_backend.shared.http.validation.invalid_authentication_request_error import (
    InvalidAuthenticationRequestError,
)

_SESSION_COOKIE_NAME = "ory_kratos_session"
_BEARER_CHALLENGE = 'Bearer realm="inframeld"'
_AUTHORIZATION_SCHEME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
_BEARER_AUTHORIZATION = re.compile(r"(?i:Bearer) +([A-Za-z0-9._~+/-]+=*)")


class IncomingCredentialMapper:
    """Select exactly one family from raw headers without provider or account I/O."""

    @staticmethod
    def unauthorized(*, invalid_token: bool = False) -> HTTPException:
        challenge = _BEARER_CHALLENGE
        if invalid_token:
            challenge += ', error="invalid_token"'
        return HTTPException(status_code=401, headers={"WWW-Authenticate": challenge})

    @staticmethod
    def _invalid_request(authorizations: Sequence[str]) -> InvalidAuthenticationRequestError:
        for value in authorizations:
            parts = value.split(None, 1)
            if parts and parts[0].casefold() == "bearer":
                return InvalidAuthenticationRequestError(
                    headers={"WWW-Authenticate": _BEARER_CHALLENGE + ', error="invalid_request"'}
                )
        return InvalidAuthenticationRequestError()

    @staticmethod
    def select(
        *, authorization_headers: Sequence[str], cookies: Mapping[str, str]
    ) -> IncomingCredential | None:
        if len(authorization_headers) > 1 or (
            authorization_headers and _SESSION_COOKIE_NAME in cookies
        ):
            raise IncomingCredentialMapper._invalid_request(authorization_headers)

        if not authorization_headers:
            raw_cookie = cookies.get(_SESSION_COOKIE_NAME)
            return BrowserSessionCredential(raw_cookie) if raw_cookie else None

        raw_header = authorization_headers[0].strip(" \t")
        scheme, separator, parameters = raw_header.partition(" ")
        if (
            not separator
            or not parameters.strip(" ")
            or _AUTHORIZATION_SCHEME.fullmatch(scheme) is None
        ):
            raise IncomingCredentialMapper._invalid_request(authorization_headers)
        if scheme.casefold() != "bearer":
            raise IncomingCredentialMapper.unauthorized()

        match = _BEARER_AUTHORIZATION.fullmatch(raw_header)
        if match is None:
            raise IncomingCredentialMapper._invalid_request(authorization_headers)
        token = match.group(1)
        try:
            if token.startswith("ifm_app_"):
                return ApplicationKeyCredential(token)
            return HumanAccessTokenCredential(token)
        except ValueError:
            raise IncomingCredentialMapper.unauthorized(invalid_token=True) from None
