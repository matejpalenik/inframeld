"""Verify real Kratos browser sessions through the backend session adapter."""

import os
from uuid import UUID, uuid4

import httpx2
import pytest
from ory_kratos_client.api.frontend_api import FrontendApi
from ory_kratos_client.api_client import ApiClient
from ory_kratos_client.configuration import Configuration

from inframeld_backend.access.application.human_session import VerifiedHumanIdentity
from inframeld_backend.access.domain.values import IdentityAuthority, IdentitySubject
from inframeld_backend.access.infrastructure.kratos_browser_session_verifier import (
    KratosBrowserSessionVerifier,
)

KRATOS_PUBLIC_URL = "http://127.0.0.1:14433"
AUTHORITY = IdentityAuthority("kratos:test")

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_KRATOS_INTEGRATION") != "1",
    reason="Set INFRAMELD_RUN_KRATOS_INTEGRATION=1 to test Kratos",
)


def _browser() -> httpx2.AsyncClient:
    """Create an independent browser with its own cookie jar."""
    return httpx2.AsyncClient(
        base_url=KRATOS_PUBLIC_URL,
        follow_redirects=False,
        timeout=15.0,
        trust_env=False,
    )


async def _register(
    browser: httpx2.AsyncClient,
) -> tuple[str, str, IdentitySubject]:
    """Register an identity and return credentials and its Kratos subject."""
    email = f"test-{uuid4().hex}@example.test"
    password = f"TestPassphrase-{uuid4().hex}!"

    started = await browser.get(
        "/self-service/registration/browser",
        headers={"Accept": "application/json"},
    )
    assert started.status_code == 200, started.text

    flow = started.json()
    csrf_token = next(
        node["attributes"]["value"]
        for node in flow["ui"]["nodes"]
        if node["attributes"]["name"] == "csrf_token"
    )

    completed = await browser.post(
        flow["ui"]["action"],
        data={
            "csrf_token": csrf_token,
            "traits.email": email,
            "password": password,
            "method": "password",
        },
        headers={"Accept": "application/json"},
    )
    assert completed.status_code in {200, 303}, completed.text

    whoami = await browser.get("/sessions/whoami")
    assert whoami.status_code == 200, whoami.text

    identity_id = whoami.json()["identity"]["id"]
    assert isinstance(identity_id, str)
    return email, password, IdentitySubject(str(UUID(identity_id)))


async def _log_in(
    browser: httpx2.AsyncClient,
    email: str,
    password: str,
) -> str:
    """Complete a password login and return the browser session cookie."""
    started = await browser.get(
        "/self-service/login/browser",
        headers={"Accept": "application/json"},
    )
    assert started.status_code == 200, started.text

    flow = started.json()
    csrf_token = next(
        node["attributes"]["value"]
        for node in flow["ui"]["nodes"]
        if node["attributes"]["name"] == "csrf_token"
    )

    completed = await browser.post(
        flow["ui"]["action"],
        data={
            "csrf_token": csrf_token,
            "identifier": email,
            "password": password,
            "method": "password",
        },
        headers={"Accept": "application/json"},
    )
    assert completed.status_code in {200, 303}, completed.text

    cookie = browser.cookies.get("ory_kratos_session")
    assert isinstance(cookie, str)
    return cookie


async def _verify(cookie: str) -> VerifiedHumanIdentity | None:
    """Resolve a browser cookie through the production Kratos adapter."""
    with ApiClient(Configuration(host=KRATOS_PUBLIC_URL)) as api_client:
        verifier = KratosBrowserSessionVerifier(FrontendApi(api_client), AUTHORITY)
        return await verifier.verify(cookie)


@pytest.mark.asyncio
async def test_browser_registration_cookie_verifies_identity() -> None:
    """Resolve the identity behind a cookie issued during registration."""
    async with _browser() as browser:
        _, _, subject = await _register(browser)
        cookie = browser.cookies.get("ory_kratos_session")
        assert isinstance(cookie, str)

        actual = await _verify(cookie)

    assert actual == VerifiedHumanIdentity(authority=AUTHORITY, subject=subject)


@pytest.mark.asyncio
async def test_password_login_cookie_verifies_same_identity() -> None:
    """A new browser login resolves to the previously registered identity."""
    async with _browser() as registration_browser:
        email, password, subject = await _register(registration_browser)

    async with _browser() as login_browser:
        cookie = await _log_in(login_browser, email, password)
        actual = await _verify(cookie)

    assert actual == VerifiedHumanIdentity(authority=AUTHORITY, subject=subject)


@pytest.mark.asyncio
async def test_logout_revokes_previous_browser_cookie() -> None:
    """A cookie that was valid before logout cannot verify afterward."""
    async with _browser() as registration_browser:
        email, password, subject = await _register(registration_browser)

    async with _browser() as browser:
        cookie = await _log_in(browser, email, password)
        assert await _verify(cookie) == VerifiedHumanIdentity(
            authority=AUTHORITY,
            subject=subject,
        )

        started = await browser.get(
            "/self-service/logout/browser",
            headers={"Accept": "application/json"},
        )
        assert started.status_code == 200, started.text

        logout_url = started.json()["logout_url"]
        assert isinstance(logout_url, str)

        completed = await browser.get(
            logout_url,
            headers={"Accept": "application/json"},
        )
        assert completed.status_code == 204, completed.text

        whoami = await browser.get("/sessions/whoami")
        assert whoami.status_code == 401

        # Check the saved value, even though logout cleared the browser cookie.
        assert await _verify(cookie) is None
