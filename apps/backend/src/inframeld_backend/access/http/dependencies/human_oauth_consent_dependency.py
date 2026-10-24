from typing import Annotated

from fastapi import Security
from fastapi.security import APIKeyCookie
from starlette.requests import Request

from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
)
from inframeld_backend.shared.http.validation.invalid_authentication_request_error import (
    InvalidAuthenticationRequestError,
)

_COOKIE_SECURITY = APIKeyCookie(
    name="ory_kratos_session",
    scheme_name="KratosSession",
    description="Kratos browser session. Cookie-authenticated writes also require a trusted Origin and X-Inframeld-CSRF: 1.",
    auto_error=False,
)


class HumanOAuthConsentDependency:
    """Extract one browser cookie and check CSRF before consent service I/O.

    This does not require local admission. The service freshly verifies the
    cookie with Kratos after reading the matching Hydra request.
    """

    def __init__(self, csrf: CSRFProtectionDependency) -> None:
        self._csrf = csrf

    async def __call__(
        self, request: Request, _cookie_schema: Annotated[str | None, Security(_COOKIE_SECURITY)]
    ) -> BrowserSessionCredential:
        if request.headers.getlist("Authorization"):
            raise InvalidAuthenticationRequestError()
        count = sum(
            part.partition("=")[0].strip() == "ory_kratos_session"
            for header in request.headers.getlist("Cookie")
            for part in header.split(";")
        )
        if count > 1:
            raise InvalidAuthenticationRequestError()
        value = request.cookies.get("ory_kratos_session")
        if not value:
            raise AuthenticationRequiredError()
        self._csrf(request)
        return BrowserSessionCredential(value)
