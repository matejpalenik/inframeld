"""Verify a browser session through Kratos."""

import asyncio
from datetime import UTC, datetime
from enum import StrEnum
from typing import final
from uuid import UUID

from ory_kratos_client.api.frontend_api import FrontendApi
from ory_kratos_client.exceptions import (
    ApiException,
    ForbiddenException,
    OpenApiException,
    UnauthorizedException,
)
from pydantic import ValidationError
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.human_session import VerifiedHumanIdentity
from inframeld_backend.access.domain.values import IdentityAuthority, IdentitySubject
from inframeld_backend.shared.application.errors import DependencyUnavailableError


class _KratosIdentityState(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


@final
class KratosBrowserSessionVerifier:
    def __init__(
        self, client: FrontendApi, authority: IdentityAuthority, timeout_seconds: float = 5.0
    ) -> None:
        self._client = client
        self._authority = authority
        self._timeout_seconds = timeout_seconds

    async def verify(self, session_cookie: str) -> VerifiedHumanIdentity | None:

        if not session_cookie:
            return None

        try:
            session = await asyncio.to_thread(
                self._client.to_session,
                cookie=f"ory_kratos_session={session_cookie}",
                _request_timeout=self._timeout_seconds,
            )
        except (UnauthorizedException, ForbiddenException):
            return None
        except (ApiException, OpenApiException, HTTPError, ValidationError) as error:
            raise DependencyUnavailableError() from error

        if session.active is None:
            raise DependencyUnavailableError()

        if not session.active:
            return None

        if (
            session.expires_at is None
            or session.expires_at.utcoffset() is None
            or session.identity is None
        ):
            raise DependencyUnavailableError()

        if session.expires_at <= datetime.now(UTC):
            return None

        try:
            state = _KratosIdentityState(session.identity.state)
            subject = IdentitySubject(str(UUID(session.identity.id)))
        except (TypeError, ValueError) as error:
            raise DependencyUnavailableError() from error

        if state is not _KratosIdentityState.ACTIVE:
            return None

        return VerifiedHumanIdentity(authority=self._authority, subject=subject)
