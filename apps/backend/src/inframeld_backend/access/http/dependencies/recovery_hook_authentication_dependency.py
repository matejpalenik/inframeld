from datetime import UTC, datetime
from hmac import compare_digest

from starlette.exceptions import HTTPException
from starlette.requests import Request


class RecoveryHookAuthenticationDependency:
    def __init__(
        self,
        *,
        current: bytes,
        retiring: bytes | None = None,
        retiring_accept_until: datetime | None = None,
    ) -> None:
        self._current = current
        self._retiring = retiring
        self._retiring_accept_until = retiring_accept_until

    def require(self, request: Request) -> None:
        values = request.headers.getlist("X-Inframeld-Recovery-Key")
        if len(values) != 1:
            raise HTTPException(401)
        try:
            supplied = values[0].encode("ascii")
        except UnicodeError:
            raise HTTPException(401) from None
        current = compare_digest(supplied, self._current)
        retiring = self._retiring
        previous = compare_digest(supplied, retiring if retiring is not None else b"")
        previous_valid = (
            retiring is not None
            and self._retiring_accept_until is not None
            and datetime.now(UTC) < self._retiring_accept_until
        )
        if not (current or (previous and previous_valid)):
            raise HTTPException(401)
