"""Check how SDK-verified Kratos sessions become human identities."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import UUID

import pytest
from ory_kratos_client.api.frontend_api import FrontendApi
from ory_kratos_client.api_client import ApiClient
from ory_kratos_client.configuration import Configuration
from ory_kratos_client.exceptions import ApiException, ForbiddenException, UnauthorizedException
from ory_kratos_client.models.identity import Identity
from ory_kratos_client.models.session import Session
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.human_session import VerifiedHumanIdentity
from inframeld_backend.access.domain.values import IdentityAuthority, IdentitySubject
from inframeld_backend.access.infrastructure.kratos_browser_session_verifier import (
    KratosBrowserSessionVerifier,
)
from inframeld_backend.shared.application.errors import DependencyUnavailableError

COOKIE = "test-session-cookie"
AUTHORITY = IdentityAuthority("kratos:installation")
IDENTITY_ID = UUID("00000000-0000-0000-0000-000000000001")


def _frontend() -> FrontendApi:
    """Create an SDK frontend whose session call will be replaced in each test."""
    return FrontendApi(ApiClient(Configuration(host="http://kratos.test")))


def _session(
    *,
    active: bool = True,
    identity_state: str = "active",
    expires_in: timedelta = timedelta(hours=1),
) -> Session:
    """Create a typed SDK session with independently variable validity."""
    identity = Identity(
        id=str(IDENTITY_ID),
        schema_id="default",
        schema_url="http://kratos.test/schemas/default",
        traits={"email": "alice@example.test"},
        state=identity_state,
    )
    return Session(
        id="00000000-0000-0000-0000-000000000002",
        active=active,
        expires_at=datetime.now(UTC) + expires_in,
        identity=identity,
    )


@pytest.mark.asyncio
async def test_active_session_returns_kratos_identity() -> None:
    """Use the Kratos identity ID rather than its session ID or email."""
    frontend = _frontend()

    with patch.object(frontend, "to_session", return_value=_session()) as to_session:
        actual = await KratosBrowserSessionVerifier(frontend, AUTHORITY).verify(COOKIE)

    to_session.assert_called_once_with(
        cookie=f"ory_kratos_session={COOKIE}",
        _request_timeout=5.0,
    )
    assert actual == VerifiedHumanIdentity(
        authority=AUTHORITY,
        subject=IdentitySubject(str(IDENTITY_ID)),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [UnauthorizedException(status=401), ForbiddenException(status=403)],
)
async def test_rejected_session_returns_no_identity(error: ApiException) -> None:
    """Reject cookies that Kratos refuses to authenticate."""
    frontend = _frontend()

    with patch.object(frontend, "to_session", side_effect=error):
        actual = await KratosBrowserSessionVerifier(frontend, AUTHORITY).verify(COOKIE)

    assert actual is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("active", "identity_state", "expires_in"),
    [
        (False, "active", timedelta(hours=1)),
        (True, "inactive", timedelta(hours=1)),
        (True, "active", timedelta(seconds=-1)),
    ],
)
async def test_unusable_session_returns_no_identity(
    active: bool,
    identity_state: str,
    expires_in: timedelta,
) -> None:
    """Reject inactive sessions, disabled identities, and expired sessions."""
    frontend = _frontend()
    session = _session(
        active=active,
        identity_state=identity_state,
        expires_in=expires_in,
    )

    with patch.object(frontend, "to_session", return_value=session):
        actual = await KratosBrowserSessionVerifier(frontend, AUTHORITY).verify(COOKIE)

    assert actual is None


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_field", ["active", "expires_at", "identity"])
async def test_incomplete_session_reports_dependency_failure(missing_field: str) -> None:
    """Fail closed when the SDK session lacks a field needed for verification."""
    frontend = _frontend()
    session = _session()
    setattr(session, missing_field, None)

    with (
        patch.object(frontend, "to_session", return_value=session),
        pytest.raises(DependencyUnavailableError),
    ):
        await KratosBrowserSessionVerifier(frontend, AUTHORITY).verify(COOKIE)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [ApiException(status=500), HTTPError("connection failed")],
)
async def test_kratos_failure_reports_dependency_failure(failure: Exception) -> None:
    """Fail closed on an unexpected Kratos response or transport error."""
    frontend = _frontend()

    with (
        patch.object(frontend, "to_session", side_effect=failure),
        pytest.raises(DependencyUnavailableError),
    ):
        await KratosBrowserSessionVerifier(frontend, AUTHORITY).verify(COOKIE)


@pytest.mark.asyncio
async def test_missing_cookie_does_not_call_kratos() -> None:
    """Return no identity when the browser supplied no session cookie."""
    frontend = _frontend()

    with patch.object(frontend, "to_session") as to_session:
        actual = await KratosBrowserSessionVerifier(frontend, AUTHORITY).verify("")

    assert actual is None
    to_session.assert_not_called()
