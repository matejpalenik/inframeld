"""Authenticate a human browser session at the HTTP boundary."""

from collections.abc import Awaitable, Callable
from http import HTTPStatus

from fastapi import HTTPException
from starlette.requests import Request

from inframeld_backend.access.application.access_authorizer import AccessContext
from inframeld_backend.access.application.human_session import (
    HumanSessionResolver,
    VerifiedHumanIdentity,
)

_SESSION_COOKIE_NAME = "ory_kratos_session"


class HumanSessionAuthentication:
    """Authenticate a browser cookie and resolve its active local human."""

    def __init__(
        self,
        verify_session: Callable[[str], Awaitable[VerifiedHumanIdentity | None]],
        resolver: HumanSessionResolver,
    ) -> None:
        self._verify_session = verify_session
        self._resolver = resolver

    async def __call__(self, request: Request) -> AccessContext:
        session_cookie = request.cookies.get(_SESSION_COOKIE_NAME)

        if not session_cookie:
            raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED)

        identity = await self._verify_session(session_cookie)

        if identity is None:
            raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED)

        return await self._resolver.resolve(identity)
