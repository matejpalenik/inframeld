"""Identify malformed or competing HTTP authentication inputs."""

from collections.abc import Mapping

from starlette.exceptions import HTTPException


class InvalidAuthenticationRequestError(HTTPException):
    """Select the reviewed 400 problem without retaining submitted credentials."""

    def __init__(self, *, headers: Mapping[str, str] | None = None) -> None:
        super().__init__(status_code=400, headers=headers)
