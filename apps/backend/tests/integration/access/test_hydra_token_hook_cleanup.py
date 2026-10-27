"""Pause after Hydra reads a token request's credentials, before token persistence."""

import asyncio
import os
from typing import Literal

import httpx2
import pytest
from ory_hydra_client import ApiClient, Configuration, OAuth2Api
from tests.support.hydra_provider import CLIENT_ID, REDIRECT_URI, hydra_test_provider
from tests.support.integration_services import HYDRA_ADMIN_URL, HYDRA_PUBLIC_URL, RECOVERY_HOOKS_URL
from tests.support.kratos_browser import create_browser, register_human
from tests.support.kratos_recovery_hooks import TEST_RECOVERY_KEY

from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.infrastructure.revokers.hydra_human_oauth_credential_revoker import (
    HydraHumanOAuthCredentialRevoker,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_HYDRA_INTEGRATION") != "1",
    reason="Requires the private integration services",
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "grant,skipped_consent,expected_status,expected_error",
    [
        ("authorization_code", False, 500, "server_error"),
        ("authorization_code", True, 500, "server_error"),
        ("refresh_token", False, 400, "invalid_request"),
    ],
)
async def test_cleanup_after_credential_validation_cannot_return_usable_credentials(
    grant: Literal["authorization_code", "refresh_token"],
    skipped_consent: bool,
    expected_status: int,
    expected_error: str,
) -> None:
    """Deleting Alice's stored grant must defeat a request already past validation."""
    sdk = ApiClient(Configuration(host=HYDRA_ADMIN_URL, retries=0, debug=False))
    try:
        async with (
            asyncio.timeout(30.0),
            hydra_test_provider() as provider,
            create_browser() as alice_browser,
            create_browser() as bob_browser,
            httpx2.AsyncClient(timeout=5.0, trust_env=False) as token_client,
            httpx2.AsyncClient(
                base_url=RECOVERY_HOOKS_URL,
                timeout=5.0,
                trust_env=False,
                headers={"X-Inframeld-Recovery-Key": TEST_RECOVERY_KEY.get_secret_value()},
            ) as hook,
        ):
            alice = await register_human(alice_browser)
            bob = await register_human(bob_browser)
            bobs_tokens = await provider.issue_tokens(bob, browser=bob_browser, remember_login=True)
            if grant == "authorization_code":
                if skipped_consent:
                    await provider.issue_tokens(
                        alice, browser=alice_browser, remember_login=True, remember_consent=True
                    )
                pending = await provider.begin_login(alice, browser=alice_browser)
                code = await provider.approve_login_and_consent(
                    pending, browser=alice_browser, remember_login=True
                )
                assert code.consent_skipped == skipped_consent
                data = {
                    "client_id": CLIENT_ID,
                    "grant_type": grant,
                    "redirect_uri": REDIRECT_URI,
                    "code": code.code.get_secret_value(),
                    "code_verifier": code.verifier.get_secret_value(),
                }
            else:
                tokens = await provider.issue_tokens(
                    alice, browser=alice_browser, remember_login=True
                )
                data = {
                    "client_id": CLIENT_ID,
                    "grant_type": grant,
                    "refresh_token": tokens.refresh_token.get_secret_value(),
                }
            plan = f"/hydra/token-plans/{alice.subject.value}/{grant}"
            assert (await hook.put(plan)).status_code == 204
            try:
                async with asyncio.TaskGroup() as tasks:
                    request = tasks.create_task(
                        token_client.post(f"{HYDRA_PUBLIC_URL}/oauth2/token", data=data)
                    )
                    observed = await hook.get(plan + "/arrived")
                    assert observed.status_code == 200
                    assert observed.json()["arrivals"] == 1
                    assert not request.done()
                    revoker = HydraHumanOAuthCredentialRevoker(OAuth2Api(sdk))
                    assert (
                        await revoker.revoke_cli_grants(alice.subject, timeout_seconds=3.0)
                    ).state == IdentityRecoveryCleanupState.CONFIRMED
                    assert (
                        await revoker.revoke_remembered_logins(alice.subject, timeout_seconds=3.0)
                    ).state == IdentityRecoveryCleanupState.CONFIRMED
                    bobs_refreshed = await provider.refresh_tokens(bobs_tokens)
                    assert bobs_refreshed is not None
                    assert await provider.token_is_active(bobs_refreshed.access_token)
                    assert (await hook.post(plan + "/release")).status_code == 204
                response = request.result()
                assert response.status_code == expected_status
                assert response.json()["error"] == expected_error
                assert "access_token" not in response.json()
                assert "refresh_token" not in response.json()
                fresh = await provider.issue_tokens(
                    alice, browser=alice_browser, remember_login=True
                )
                assert await provider.token_is_active(fresh.access_token)
                assert await provider.login_can_skip(bob_browser)
            finally:
                assert (await hook.delete(plan)).status_code == 204
    finally:
        sdk.rest_client.pool_manager.clear()
