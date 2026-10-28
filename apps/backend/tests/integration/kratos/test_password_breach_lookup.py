"""Keep real Kratos password validation independent of the public HIBP service."""

import hashlib
import os
from uuid import uuid4

import httpx2
import pytest
from pydantic import BaseModel
from tests.support.integration_services import PASSWORD_BREACHES_URL
from tests.support.kratos_browser import (
    BrowserFlow,
    create_browser,
    read_browser_csrf_token,
    register_human,
)
from tests.support.password_breaches import BREACHED_PASSWORD, create_client

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_KRATOS_INTEGRATION") != "1",
    reason="Requires the private Kratos and password-breach fixture services",
)


class _LookupObservation(BaseModel):
    requests: int


@pytest.mark.asyncio
async def test_fixture_requires_explicit_test_ca_trust() -> None:
    async with create_client() as trusted:
        assert (await trusted.get("/health/ready")).status_code == 200

    async with httpx2.AsyncClient(timeout=2, trust_env=False) as untrusted:
        with pytest.raises(httpx2.ConnectError, match="CERTIFICATE_VERIFY_FAILED"):
            await untrusted.get(f"{PASSWORD_BREACHES_URL}/health/ready")


async def _lookup_count(password: str) -> int:
    prefix = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest()[:5].upper()
    async with create_client() as client:
        response = await client.get(f"/observations/{prefix}")
        assert response.status_code == 200
        return _LookupObservation.model_validate_json(response.content).requests


@pytest.mark.asyncio
async def test_registration_checks_ordinary_password_against_local_breach_service() -> None:
    async with create_browser() as browser:
        human = await register_human(browser)
        assert await _lookup_count(human.password) >= 1
        assert (await browser.get("/sessions/whoami")).status_code == 200


@pytest.mark.asyncio
async def test_breached_password_creates_neither_identity_nor_authenticated_session() -> None:
    email = f"breached-{uuid4().hex}@example.test"
    async with create_browser() as browser:
        started = await browser.get(
            "/self-service/registration/browser", headers={"Accept": "application/json"}
        )
        assert started.status_code == 200
        flow = BrowserFlow.model_validate_json(started.content)
        rejected = await browser.post(
            flow.ui.action,
            data={
                "csrf_token": read_browser_csrf_token(flow),
                "traits.email": email,
                "password": BREACHED_PASSWORD,
                "method": "password",
            },
            headers={"Accept": "application/json"},
        )
        assert rejected.status_code == 400
        assert await _lookup_count(BREACHED_PASSWORD) >= 1
        assert (await browser.get("/sessions/whoami")).status_code == 401

        # Reusing the email successfully proves the rejected attempt created no identity.
        human = await register_human(browser, email=email)
        assert human.email == email
