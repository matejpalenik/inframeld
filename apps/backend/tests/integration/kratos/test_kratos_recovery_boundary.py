"""Check browser authentication before and after redeeming a recovery code."""

import asyncio
import os
import re

import httpx2
import pytest
from ory_kratos_client.models.recovery_flow import RecoveryFlow
from ory_kratos_client.models.recovery_flow_state import RecoveryFlowState
from tests.support.kratos_browser import BrowserFlow, WhoamiResponse, create_browser, register_human

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_KRATOS_INTEGRATION") != "1",
    reason="Requires Kratos integration services",
)


def _csrf_token(flow: BrowserFlow) -> str:
    """Require the single CSRF token supplied for this recovery form."""
    values = [
        node.attributes.value for node in flow.ui.nodes if node.attributes.name == "csrf_token"
    ]
    assert len(values) == 1
    token = values[0]
    assert isinstance(token, str)
    return token


async def _request_recovery_code(browser: httpx2.AsyncClient, email: str) -> BrowserFlow:
    """Request a code and return the updated browser form used to redeem it."""
    started = await browser.get(
        "/self-service/recovery/browser", headers={"Accept": "application/json"}
    )
    assert started.status_code == 200, started.text
    flow = BrowserFlow.model_validate_json(started.text)

    requested = await browser.post(
        flow.ui.action,
        data={"csrf_token": _csrf_token(flow), "email": email, "method": "code"},
        headers={"Accept": "application/json"},
    )
    assert requested.status_code == 200, requested.text
    assert RecoveryFlow.model_validate_json(requested.text).state == RecoveryFlowState.SENT_EMAIL
    return BrowserFlow.model_validate_json(requested.text)


async def _wait_for_recovery_email(email: str) -> str:
    """Wait for Kratos's message to reach the test mailbox for this address."""
    async with httpx2.AsyncClient(
        base_url="http://127.0.0.1:18025", timeout=5.0, trust_env=False
    ) as mailbox:
        for _ in range(80):
            message = await mailbox.get("/view/latest.txt", params={"query": f"to:{email}"})
            if message.status_code == 200:
                assert message.text.strip()
                return message.text

            assert message.status_code == 404, message.text
            await asyncio.sleep(0.25)

    pytest.fail("Recovery email was not delivered to the test mailbox.")


@pytest.mark.asyncio
async def test_recovery_does_not_authenticate_browser() -> None:
    """Deliver a recovery code while leaving the requesting browser signed out."""
    async with create_browser() as registration_browser:
        human = await register_human(registration_browser)

    async with create_browser() as browser:
        await _request_recovery_code(browser, human.email)
        assert browser.cookies.get("ory_kratos_session") is None
        assert (await browser.get("/sessions/whoami")).status_code == 401
        await _wait_for_recovery_email(human.email)


@pytest.mark.asyncio
async def test_valid_recovery_code_authenticates_same_identity() -> None:
    """Redeem the emailed code in the requesting browser and verify its identity."""
    async with create_browser() as registration_browser:
        human = await register_human(registration_browser)

    async with create_browser() as browser:
        pending_flow = await _request_recovery_code(browser, human.email)
        assert (await browser.get("/sessions/whoami")).status_code == 401

        mail_text = await _wait_for_recovery_email(human.email)
        codes = re.findall(r"(?<![A-Za-z0-9])\d{6,8}(?![A-Za-z0-9])", mail_text)
        assert len(codes) == 1, "Expected one numeric code in the recovery email."

        redeemed = await browser.post(
            pending_flow.ui.action,
            data={
                "csrf_token": _csrf_token(pending_flow),
                "code": codes[0],
                "method": "code",
            },
            headers={"Accept": "text/html"},
        )
        assert redeemed.status_code in {302, 303}, redeemed.text

        whoami = await browser.get("/sessions/whoami")
        assert whoami.status_code == 200, whoami.text
        identity = WhoamiResponse.model_validate_json(whoami.text).identity
        assert str(identity.id) == human.subject.value
