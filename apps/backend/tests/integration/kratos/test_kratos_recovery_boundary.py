"""Check browser authentication before and after redeeming a recovery code."""

import os

import pytest
from tests.support.kratos_browser import WhoamiResponse, create_browser, register_human
from tests.support.kratos_recovery import (
    redeem_recovery_code,
    request_recovery_code,
    wait_for_recovery_code,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_KRATOS_INTEGRATION") != "1",
    reason="Requires Kratos integration services",
)


@pytest.mark.asyncio
async def test_recovery_does_not_authenticate_browser() -> None:
    """Requesting an email must leave the requesting browser signed out."""
    async with create_browser() as registration_browser:
        human = await register_human(registration_browser)

    async with create_browser() as browser:
        await request_recovery_code(browser, human.email)

        assert browser.cookies.get("ory_kratos_session") is None
        assert (await browser.get("/sessions/whoami")).status_code == 401

        await wait_for_recovery_code(human.email)


@pytest.mark.asyncio
async def test_valid_recovery_code_authenticates_same_identity() -> None:
    """Redeeming the code must authenticate the human who owns that address."""
    async with create_browser() as registration_browser:
        human = await register_human(registration_browser)

    async with create_browser() as browser:
        pending_flow = await request_recovery_code(browser, human.email)
        assert (await browser.get("/sessions/whoami")).status_code == 401

        code = await wait_for_recovery_code(human.email)
        redeemed = await redeem_recovery_code(browser, pending_flow, code)
        assert redeemed.status_code in {302, 303}, "Recovery did not finish."

        whoami = await browser.get("/sessions/whoami")
        assert whoami.status_code == 200, "Recovery did not authenticate the browser."

        identity = WhoamiResponse.model_validate_json(whoami.text).identity
        assert str(identity.id) == human.subject.value
