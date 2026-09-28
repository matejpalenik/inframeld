"""Check the CSRF header on cookie-authenticated HTTP writes"""

from pydantic import HttpUrl, ValidationError
from starlette.requests import Request

from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_CSRF_HEADER = "X-Inframeld-CSRF"


class CSRFProtectionDependency:
    """Require the browser's CSRF header before a protected operation can run"""

    def __init__(self, trusted_origins: tuple[HttpUrl, ...]) -> None:
        self._trusted_origins = frozenset(trusted_origins)

    def __call__(self, request: Request) -> None:
        if request.method in _SAFE_METHODS:
            return

        if request.headers.get(_CSRF_HEADER) != "1":
            raise AccessDeniedError()

        origins = request.headers.getlist("Origin")

        if len(origins) != 1:
            raise AccessDeniedError()

        try:
            origin = HttpUrl(origins[0])
        except ValidationError:
            raise AccessDeniedError() from None

        if (
            origin.path != "/"
            or origin.query is not None
            or origin.fragment is not None
            or origin.username is not None
            or origin.password is not None
            or origins[0] != str(origin).removesuffix("/")
            or origin not in self._trusted_origins
        ):
            raise AccessDeniedError()
