"""Verify registration, login, and logout through the real Kratos browser boundary."""

import os

import pytest
from ory_kratos_client.api.frontend_api import FrontendApi
from ory_kratos_client.api_client import ApiClient
from ory_kratos_client.configuration import Configuration
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
pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_KRATOS_INTEGRATION") != "1",
    reason="Requires Kratos integration services",
)


async def _verify(credential: BrowserSessionCredential) -> VerifiedHumanIdentityDTO | None:
    """Verify the saved credential through the SDK and release its HTTP pools."""
    client = ApiClient(Configuration(host=KRATOS_PUBLIC_URL))
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
async def test_logout_revokes_previous_browser_cookie() -> None:
    """Reject a saved credential after its browser session logs out."""
    async with create_browser() as registration_browser:
        human = await register_human(registration_browser)
    async with create_browser() as browser:
        credential = await login_human(browser, human)
        assert await _verify(credential) == VerifiedHumanIdentityDTO(AUTHORITY, human.subject)
        await logout_human(browser)
        assert await _verify(credential) is None
