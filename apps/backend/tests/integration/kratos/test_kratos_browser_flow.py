"""Verify registration, login, and logout through the real Kratos browser boundary."""

import asyncio
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ory_kratos_client.api.frontend_api import FrontendApi
from ory_kratos_client.api_client import ApiClient
from ory_kratos_client.configuration import Configuration
from ory_kratos_client.models.session import Session
from tests.support.kratos_browser import (
    KRATOS_PUBLIC_URL,
    create_browser,
    login_human,
    logout_human,
    register_human,
)

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.infrastructure.verifiers.kratos_browser_session_verifier import (
    KratosBrowserSessionVerifier,
)

AUTHORITY = IdentityAuthority("kratos:test")
EXPIRING_KRATOS_PUBLIC_URL = "http://127.0.0.1:14435"

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_KRATOS_INTEGRATION") != "1",
    reason="Requires Kratos integration services",
)


async def _verify(
    credential: BrowserSessionCredential,
    *,
    public_url: str = KRATOS_PUBLIC_URL,
) -> VerifiedHumanIdentityDTO | None:
    """Verify a saved cookie through the selected Kratos service and release its HTTP pools."""
    client = ApiClient(Configuration(host=public_url))
    try:
        return await KratosBrowserSessionVerifier(FrontendApi(client), AUTHORITY).verify(credential)
    finally:
        client.rest_client.pool_manager.clear()


@pytest.mark.asyncio
async def test_browser_registration_cookie_verifies_identity() -> None:
    """Resolve the identity behind a cookie issued during registration."""
    async with create_browser() as browser:
        human = await register_human(browser)
        assert await _verify(human.credential) == VerifiedHumanIdentityDTO(AUTHORITY, human.subject)


@pytest.mark.asyncio
async def test_password_login_cookie_verifies_same_identity() -> None:
    """Resolve a new browser login to the previously registered identity."""
    async with create_browser() as registration_browser:
        human = await register_human(registration_browser)
    async with create_browser() as browser:
        credential = await login_human(browser, human)
        assert await _verify(credential) == VerifiedHumanIdentityDTO(AUTHORITY, human.subject)


@pytest.mark.asyncio
async def test_expired_browser_cookie_is_rejected() -> None:
    """Reject the original cookie after Kratos's recorded session expiry."""
    async with create_browser() as registration_browser:
        human = await register_human(registration_browser)

    async with create_browser(public_url=EXPIRING_KRATOS_PUBLIC_URL) as browser:
        credential = await login_human(browser, human)

        current = await browser.get("/sessions/whoami")
        assert current.status_code == 200, current.text

        session = Session.model_validate_json(current.text)
        expires_at = session.expires_at
        assert expires_at is not None
        assert expires_at.utcoffset() is not None
        assert expires_at > datetime.now(UTC)

        assert await _verify(
            credential, public_url=EXPIRING_KRATOS_PUBLIC_URL
        ) == VerifiedHumanIdentityDTO(AUTHORITY, human.subject)

        remaining_seconds = (expires_at - datetime.now(UTC)).total_seconds()
        await asyncio.sleep(max(0.0, remaining_seconds) + 0.25)

        # Send the saved value explicitly: the browser's cookie jar may discard
        # an expired cookie before making the request.
        async with asyncio.timeout(5):
            while True:
                expired = await browser.get(
                    "/sessions/whoami",
                    headers={"Cookie": f"ory_kratos_session={credential.value}"},
                )
                if expired.status_code == 401:
                    break
                assert expired.status_code == 200, expired.text
                await asyncio.sleep(0.1)

        assert await _verify(credential, public_url=EXPIRING_KRATOS_PUBLIC_URL) is None


@pytest.mark.asyncio
async def test_logout_revokes_previous_browser_cookie() -> None:
    """Reject a saved credential after its browser session logs out."""
    async with create_browser() as registration_browser:
        human = await register_human(registration_browser)
    async with create_browser() as browser:
        credential = await login_human(browser, human)
        assert await _verify(credential) == VerifiedHumanIdentityDTO(AUTHORITY, human.subject)
        await logout_human(browser)
        assert await _verify(credential) is None


@pytest.mark.asyncio
async def test_disabled_kratos_identity_rejects_existing_browser_cookie() -> None:
    """Reject an already issued session after kratos disables its identity."""

    async with create_browser() as browser:
        human = await register_human(browser)
        assert await _verify(human.credential) == VerifiedHumanIdentityDTO(AUTHORITY, human.subject)

        repository_root = Path(__file__).resolve().parents[5]  # noqa: ASYNC240

        result = await asyncio.to_thread(
            subprocess.run,
            [
                str(repository_root / "scripts/dev-compose.sh"),
                "test-kratos-disable-identity",
                human.subject.value,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        assert result.returncode == 0, result.stderr

        assert await _verify(human.credential) is None
