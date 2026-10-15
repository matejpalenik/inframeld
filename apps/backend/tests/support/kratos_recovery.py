"""Drive Kratos code recovery through its browser forms and test mailbox."""

import asyncio
import re
from typing import Literal
from uuid import UUID

import httpx2
from pydantic import SecretStr

from tests.support.integration_services import MAILPIT_URL
from tests.support.kratos_browser import BrowserFlow


class RecoveryFlowResponse(BrowserFlow):
    """Read the recovery flow's ID, state and CSRF-protected browser form."""

    id: UUID
    state: Literal["choose_method", "sent_email", "passed_challenge"]


def _csrf_token(flow: BrowserFlow) -> str:
    """Require exactly one textual CSRF token before submitting a form."""

    values = [
        node.attributes.value for node in flow.ui.nodes if node.attributes.name == "csrf_token"
    ]

    assert len(values) == 1, "Expected one CSRF token in the recovery form."

    token = values[0]

    assert isinstance(token, str), "Expected a textual recovery CSRF token."

    return token


async def request_recovery_code(browser: httpx2.AsyncClient, email: str) -> RecoveryFlowResponse:
    """Request a recovery email and return the form used to submit its code."""

    started = await browser.get(
        "/self-service/recovery/browser", headers={"Accept": "application/json"}
    )
    assert started.status_code == 200, "Could not start recovery."

    flow = RecoveryFlowResponse.model_validate_json(started.text)

    requested = await browser.post(
        flow.ui.action,
        data={"csrf_token": _csrf_token(flow), "email": email, "method": "code"},
        headers={"Accept": "application/json"},
    )
    assert requested.status_code == 200, "Could not request the recovery code."

    pending = RecoveryFlowResponse.model_validate_json(requested.text)
    assert pending.id == flow.id, "Kratos changed the recovery flow."
    assert pending.state == "sent_email", "Kratos did not reach the email-sent state."

    return pending


async def wait_for_recovery_code(email: str) -> SecretStr:
    """Wait up to 20 seconds for this account's code without printing it."""

    async with (
        httpx2.AsyncClient(base_url=MAILPIT_URL, timeout=2.0, trust_env=False) as mailbox,
        asyncio.timeout(20.0),
    ):
        while True:
            message = await mailbox.get("/view/latest.txt", params={"query": f"to:{email}"})

            if message.status_code == 200:
                codes = re.findall(r"(?<![A-Za-z0-9])\d{6,8}(?![A-Za-z0-9])", message.text)
                assert len(codes) == 1, "Expected one recovery code in the test email."
                return SecretStr(codes[0])

            assert message.status_code == 404, "Could not inspect the test mailbox."
            await asyncio.sleep(0.25)


async def redeem_recovery_code(
    browser: httpx2.AsyncClient, flow: RecoveryFlowResponse, code: SecretStr
) -> httpx2.Response:
    """Return Kratos's response after submitting a valid or invalid code."""

    return await browser.post(
        flow.ui.action,
        data={
            "csrf_token": _csrf_token(flow),
            "code": code.get_secret_value(),
            "method": "code",
        },
        headers={"Accept": "text/html"},
    )
