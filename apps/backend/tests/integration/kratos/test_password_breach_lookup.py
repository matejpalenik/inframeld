"""Keep real Kratos password validation independent of the public HIBP service."""

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
from tests.support.password_breaches import (
    BREACHED_PASSWORD,
    BREACHED_PASSWORD_SHA1,
    CLEAN_PASSWORD,
    CLEAN_PASSWORD_PREFIX,
    create_client,
)

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


async def _lookup_count(prefix: str) -> int:
    async with create_client() as client:
        response = await client.get(f"/observations/{prefix}")
        assert response.status_code == 200
        return _LookupObservation.model_validate_json(response.content).requests


@pytest.mark.asyncio
async def test_registration_checks_ordinary_password_against_local_breach_service() -> None:
    lookups_before = await _lookup_count(CLEAN_PASSWORD_PREFIX)
    async with create_browser() as browser:
        completed = await _submit_registration(
            browser, email=f"clean-{uuid4().hex}@example.test", password=CLEAN_PASSWORD
        )
        assert completed.status_code == 200
        assert await _lookup_count(CLEAN_PASSWORD_PREFIX) > lookups_before
        assert (await browser.get("/sessions/whoami")).status_code == 200


async def _submit_registration(
    browser: httpx2.AsyncClient, *, email: str, password: str
) -> httpx2.Response:
    started = await browser.get(
        "/self-service/registration/browser", headers={"Accept": "application/json"}
    )
    assert started.status_code == 200
    flow = BrowserFlow.model_validate_json(started.content)
    return await browser.post(
        flow.ui.action,
        data={
            "csrf_token": read_browser_csrf_token(flow),
            "traits.email": email,
            "password": password,
            "method": "password",
        },
        headers={"Accept": "application/json"},
    )


@pytest.mark.asyncio
async def test_breached_password_creates_neither_identity_nor_authenticated_session() -> None:
    lookups_before = await _lookup_count(BREACHED_PASSWORD_SHA1[:5])
    email = f"breached-{uuid4().hex}@example.test"
    async with create_browser() as browser:
        rejected = await _submit_registration(browser, email=email, password=BREACHED_PASSWORD)
        assert rejected.status_code == 400
        assert await _lookup_count(BREACHED_PASSWORD_SHA1[:5]) > lookups_before
        assert (await browser.get("/sessions/whoami")).status_code == 401

        # Reusing the email successfully proves the rejected attempt created no identity.
        human = await register_human(browser, email=email)
        assert human.email == email
