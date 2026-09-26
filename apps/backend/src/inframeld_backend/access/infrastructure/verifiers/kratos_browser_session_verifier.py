"""Verify a browser session through Kratos."""

import asyncio
from datetime import UTC, datetime
from enum import StrEnum
from typing import final, override
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

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.browser_session_verifier import (
    BrowserSessionVerifier,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)


class _KratosIdentityState(StrEnum):
    """Narrow the provider identity-state vocabulary before local authentication."""

    ACTIVE = "active"
    INACTIVE = "inactive"


@final
class KratosBrowserSessionVerifier(BrowserSessionVerifier):
    """Verify Kratos sessions through its SDK and normalize identity and availability outcomes.

    SDK calls run in a worker thread with a bounded network timeout. This adapter
    checks session expiry and provider identity state without reading local grants.
    The application lifespan owns the injected SDK connection pool.
    """

    def __init__(
        self, client: FrontendApi, authority: IdentityAuthority, timeout_seconds: float = 5.0
    ) -> None:
        """Retain the SDK API, trusted authority, and per-call timeout without network I/O."""
        self._client = client
        self._authority = authority
        self._timeout_seconds = timeout_seconds

    @override
    async def verify(self, credential: BrowserSessionCredential) -> VerifiedHumanIdentityDTO | None:
        """Ask Kratos for this session and reject inactive, expired, or disabled provider identities."""
        try:
            session = await asyncio.to_thread(
                self._client.to_session,
                cookie=f"ory_kratos_session={credential.value}",
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

        return VerifiedHumanIdentityDTO(authority=self._authority, subject=subject)
