"""Qualify HTTP ordering around cleanup, without controlling Hydra's internal races."""

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx2
import pytest
from ory_hydra_client import ApiClient, Configuration, OAuth2Api
from tests.support.hydra_provider import (
    HydraTestProvider,
    IssuedHydraTokensDTO,
    hydra_test_provider,
)
from tests.support.hydra_token_request_gate import HydraTokenRequestGate
from tests.support.integration_services import HYDRA_ADMIN_URL
from tests.support.kratos_browser import RegisteredHumanDTO, create_browser, register_human

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


@dataclass(frozen=True, slots=True)
class HydraIssuanceScenario:
    provider: HydraTestProvider
    gate: HydraTokenRequestGate
    revoker: HydraHumanOAuthCredentialRevoker
    alice: RegisteredHumanDTO
    bobs_tokens: IssuedHydraTokensDTO
    bobs_browser: httpx2.AsyncClient


def _browser() -> httpx2.AsyncClient:
    return httpx2.AsyncClient(timeout=5.0, follow_redirects=False, trust_env=False)


@asynccontextmanager
async def _scenario() -> AsyncGenerator[HydraIssuanceScenario]:
    """Own each request task inside this bounded lifetime, before transport teardown."""
    gate = HydraTokenRequestGate(httpx2.AsyncHTTPTransport(retries=0, trust_env=False))
    sdk = ApiClient(Configuration(host=HYDRA_ADMIN_URL, retries=0, debug=False))
    try:
        async with (
            asyncio.timeout(30.0),
            hydra_test_provider(transport=gate) as provider,
            create_browser() as registration,
            create_browser() as bobs_registration,
            _browser() as bobs_browser,
        ):
            alice = await register_human(registration)
            bob = await register_human(bobs_registration)
            bobs_tokens = await provider.issue_tokens(
                bob, browser=bobs_browser, remember_login=True
            )
            yield HydraIssuanceScenario(
                provider,
                gate,
                HydraHumanOAuthCredentialRevoker(OAuth2Api(sdk)),
                alice,
                bobs_tokens,
                bobs_browser,
            )
    finally:
        await gate.aclose()
        sdk.rest_client.pool_manager.clear()


async def _clean_up_alice(scenario: HydraIssuanceScenario) -> None:
    assert await scenario.revoker.revoke_cli_grants(
        scenario.alice.subject, timeout_seconds=3.0
    ) == (IdentityRecoveryCleanupState.CONFIRMED)
    assert (
        await scenario.revoker.revoke_remembered_logins(scenario.alice.subject, timeout_seconds=3.0)
        == IdentityRecoveryCleanupState.CONFIRMED
    )
    assert await scenario.provider.token_is_active(scenario.bobs_tokens.access_token)


async def _assert_bob_still_works(scenario: HydraIssuanceScenario) -> None:
    assert await scenario.provider.token_is_active(scenario.bobs_tokens.access_token)
    refreshed = await scenario.provider.refresh_tokens(scenario.bobs_tokens)
    assert refreshed is not None
    assert await scenario.provider.token_is_active(refreshed.access_token)
    assert await scenario.provider.login_can_skip(scenario.bobs_browser)


async def _assert_revoked(provider: HydraTestProvider, tokens: IssuedHydraTokensDTO) -> None:
    assert not await provider.token_is_active(tokens.access_token)
    assert await provider.refresh_tokens(tokens) is None


@pytest.mark.asyncio
async def test_login_approved_after_cleanup_can_issue_new_credentials() -> None:
    """Bulk deletion cannot prevent a prepared but not yet approved login from finishing."""
    async with _scenario() as scenario, _browser() as browser:
        pending = await scenario.provider.begin_login(scenario.alice, browser=browser)
        await _clean_up_alice(scenario)
        code = await scenario.provider.approve_login_and_consent(
            pending, browser=browser, remember_login=True
        )
        tokens = await scenario.provider.exchange_authorization_code(code)
        assert tokens is not None
        assert await scenario.provider.token_is_active(tokens.access_token)
        assert await scenario.provider.refresh_tokens(tokens) is not None
        await _assert_bob_still_works(scenario)


@pytest.mark.asyncio
@pytest.mark.parametrize("skipped_consent", [False, True])
async def test_code_issued_before_cleanup_cannot_be_exchanged_afterward(
    skipped_consent: bool,
) -> None:
    """Revocation must also invalidate a code which the CLI has not exchanged yet."""
    async with _scenario() as scenario, _browser() as browser:
        previous = await scenario.provider.issue_tokens(
            scenario.alice,
            browser=browser,
            remember_login=True,
            remember_consent=skipped_consent,
        )
        pending = await scenario.provider.begin_login(scenario.alice, browser=browser)
        code = await scenario.provider.approve_login_and_consent(
            pending,
            browser=browser,
            remember_login=True,
            remember_consent=skipped_consent,
        )
        assert code.consent_skipped == skipped_consent
        assert (
            await scenario.revoker.revoke_cli_grants(scenario.alice.subject, timeout_seconds=3.0)
            == IdentityRecoveryCleanupState.CONFIRMED
        )
        assert await scenario.provider.exchange_authorization_code(code) is None
        await _assert_revoked(scenario.provider, previous)
        await _assert_bob_still_works(scenario)


@pytest.mark.asyncio
async def test_successful_code_response_delivered_after_cleanup_contains_revoked_credentials() -> (
    None
):
    """Receiving an earlier 200 later cannot restore the grant removed by cleanup."""
    async with _scenario() as scenario:
        code = await scenario.provider.approve_login_and_consent(
            await scenario.provider.begin_login(scenario.alice)
        )
        scenario.gate.arm("after_response")
        async with asyncio.TaskGroup() as tasks:
            exchange = tasks.create_task(scenario.provider.exchange_authorization_code(code))
            await scenario.gate.wait_until_paused()
            assert not exchange.done()
            await _clean_up_alice(scenario)
            scenario.gate.release()
        tokens = exchange.result()
        assert tokens is not None
        await _assert_revoked(scenario.provider, tokens)
        await _assert_bob_still_works(scenario)


@pytest.mark.asyncio
async def test_refresh_dispatched_after_cleanup_is_denied() -> None:
    """The paused request has not reached Hydra when deletion completes."""
    async with _scenario() as scenario:
        previous = await scenario.provider.issue_tokens(scenario.alice)
        scenario.gate.arm("before_request")
        async with asyncio.TaskGroup() as tasks:
            refresh = tasks.create_task(scenario.provider.refresh_tokens(previous))
            await scenario.gate.wait_until_paused()
            assert not refresh.done()
            await _clean_up_alice(scenario)
            scenario.gate.release()
        assert refresh.result() is None
        await _assert_revoked(scenario.provider, previous)
        await _assert_bob_still_works(scenario)


@pytest.mark.asyncio
async def test_successful_refresh_response_delivered_after_cleanup_is_already_revoked() -> None:
    """Cleanup covers rotated descendants even if the CLI receives them afterward."""
    async with _scenario() as scenario:
        previous = await scenario.provider.issue_tokens(scenario.alice)
        scenario.gate.arm("after_response")
        async with asyncio.TaskGroup() as tasks:
            refresh = tasks.create_task(scenario.provider.refresh_tokens(previous))
            await scenario.gate.wait_until_paused()
            assert not refresh.done()
            await _clean_up_alice(scenario)
            scenario.gate.release()
        replacement = refresh.result()
        assert replacement is not None
        await _assert_revoked(scenario.provider, previous)
        await _assert_revoked(scenario.provider, replacement)
        await _assert_bob_still_works(scenario)


@pytest.mark.asyncio
async def test_fresh_login_after_cleanup_issues_working_credentials() -> None:
    async with _scenario() as scenario, _browser() as browser:
        previous = await scenario.provider.issue_tokens(scenario.alice)
        await _clean_up_alice(scenario)
        await _assert_revoked(scenario.provider, previous)
        fresh = await scenario.provider.issue_tokens(
            scenario.alice, browser=browser, remember_login=True
        )
        assert await scenario.provider.token_is_active(fresh.access_token)
        refreshed = await scenario.provider.refresh_tokens(fresh)
        assert refreshed is not None
        assert await scenario.provider.token_is_active(refreshed.access_token)
        await _assert_bob_still_works(scenario)
