"""Qualify individual cleanup targets against the pinned real Hydra server."""

import os
from collections.abc import AsyncGenerator, Iterator
from unittest.mock import patch

import httpx2
import pytest
import pytest_asyncio
from ory_hydra_client import ApiClient, Configuration, OAuth2Api
from tests.support.hydra_provider import HydraTestProvider, hydra_test_provider
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


@pytest_asyncio.fixture
async def provider() -> AsyncGenerator[HydraTestProvider]:
    async with hydra_test_provider() as provider:
        yield provider


@pytest_asyncio.fixture
async def alice(provider: HydraTestProvider) -> RegisteredHumanDTO:
    async with create_browser() as browser:
        return await register_human(browser)


@pytest.fixture
def hydra_sdk() -> Iterator[OAuth2Api]:
    sdk = ApiClient(Configuration(host=HYDRA_ADMIN_URL, retries=0, debug=False))
    try:
        yield OAuth2Api(sdk)
    finally:
        sdk.rest_client.pool_manager.clear()


@pytest.fixture
def revoker(hydra_sdk: OAuth2Api) -> HydraHumanOAuthCredentialRevoker:
    return HydraHumanOAuthCredentialRevoker(hydra_sdk)


def _browser() -> httpx2.AsyncClient:
    return httpx2.AsyncClient(timeout=5.0, follow_redirects=False, trust_env=False)


@pytest.mark.asyncio
async def test_grant_cleanup_invalidates_access_and_refresh_but_keeps_remembered_login(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
) -> None:
    """Removing Alice's token grant and forgetting her login are separate operations."""
    async with _browser() as browser:
        tokens = await provider.issue_tokens(alice, browser=browser, remember_login=True)
        assert await provider.token_is_active(tokens.access_token)
        assert await provider.login_can_skip(browser)

        assert await revoker.revoke_grant(tokens.consent_request_id, timeout_seconds=3.0) == (
            IdentityRecoveryCleanupState.CONFIRMED
        )

        assert not await provider.token_is_active(tokens.access_token)
        assert await provider.refresh_tokens(tokens) is None
        assert await provider.login_can_skip(browser)


@pytest.mark.asyncio
async def test_login_cleanup_prevents_skip_but_does_not_revoke_issued_tokens(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
) -> None:
    async with _browser() as browser:
        tokens = await provider.issue_tokens(alice, browser=browser, remember_login=True)
        assert await provider.login_can_skip(browser)

        assert await revoker.revoke_login(tokens.login_session_id, timeout_seconds=3.0) == (
            IdentityRecoveryCleanupState.CONFIRMED
        )

        assert not await provider.login_can_skip(browser)
        assert await provider.token_is_active(tokens.access_token)
        assert await provider.refresh_tokens(tokens) is not None


@pytest.mark.asyncio
async def test_consent_cleanup_includes_rotated_refresh_descendants(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
) -> None:
    """The original consent ID still identifies tokens issued by a later refresh."""
    tokens = await provider.issue_tokens(alice)
    refreshed = await provider.refresh_tokens(tokens)
    assert refreshed is not None
    assert await provider.token_is_active(refreshed.access_token)

    assert await revoker.revoke_grant(tokens.consent_request_id, timeout_seconds=3.0) == (
        IdentityRecoveryCleanupState.CONFIRMED
    )

    assert not await provider.token_is_active(tokens.access_token)
    assert not await provider.token_is_active(refreshed.access_token)
    assert await provider.refresh_tokens(refreshed) is None


@pytest.mark.asyncio
async def test_exact_cleanup_preserves_another_alice_login_and_bobs_credentials(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
) -> None:
    """Neither the shared subject nor the shared CLI client broadens the selected target."""
    async with create_browser() as registration:
        bob = await register_human(registration)
    async with _browser() as old_browser, _browser() as other_browser, _browser() as bob_browser:
        old = await provider.issue_tokens(alice, browser=old_browser, remember_login=True)
        other = await provider.issue_tokens(alice, browser=other_browser, remember_login=True)
        bobs = await provider.issue_tokens(bob, browser=bob_browser, remember_login=True)
        assert old.login_session_id != other.login_session_id
        assert old.consent_request_id != other.consent_request_id

        assert await revoker.revoke_grant(old.consent_request_id, timeout_seconds=3.0) == (
            IdentityRecoveryCleanupState.CONFIRMED
        )
        assert await revoker.revoke_login(old.login_session_id, timeout_seconds=3.0) == (
            IdentityRecoveryCleanupState.CONFIRMED
        )

        assert not await provider.token_is_active(old.access_token)
        assert await provider.refresh_tokens(old) is None
        assert not await provider.login_can_skip(old_browser)
        for tokens, browser in ((other, other_browser), (bobs, bob_browser)):
            assert await provider.token_is_active(tokens.access_token)
            assert await provider.refresh_tokens(tokens) is not None
            assert await provider.login_can_skip(browser)


@pytest.mark.asyncio
async def test_repeating_old_cleanup_preserves_a_later_login_in_the_same_browser(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
) -> None:
    """A delayed retry of Alice's old cleanup must not log her out again."""
    async with _browser() as browser:
        old = await provider.issue_tokens(alice, browser=browser, remember_login=True)
        assert await revoker.revoke_grant(old.consent_request_id, timeout_seconds=3.0) == (
            IdentityRecoveryCleanupState.CONFIRMED
        )
        assert await revoker.revoke_login(old.login_session_id, timeout_seconds=3.0) == (
            IdentityRecoveryCleanupState.CONFIRMED
        )
        later = await provider.issue_tokens(alice, browser=browser, remember_login=True)
        assert later.login_session_id != old.login_session_id
        assert later.consent_request_id != old.consent_request_id

        assert await revoker.revoke_grant(old.consent_request_id, timeout_seconds=3.0) == (
            IdentityRecoveryCleanupState.CONFIRMED
        )
        assert await revoker.revoke_login(old.login_session_id, timeout_seconds=3.0) == (
            IdentityRecoveryCleanupState.CONFIRMED
        )

        assert await provider.token_is_active(later.access_token)
        assert await provider.refresh_tokens(later) is not None
        assert await provider.login_can_skip(browser)


@pytest.mark.asyncio
async def test_grant_cleanup_preserves_another_grant_from_the_same_remembered_login(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
) -> None:
    async with _browser() as browser:
        first = await provider.issue_tokens(alice, browser=browser, remember_login=True)
        second = await provider.issue_tokens(alice, browser=browser, remember_login=True)
        assert first.login_session_id == second.login_session_id
        assert first.consent_request_id != second.consent_request_id

        assert await revoker.revoke_grant(first.consent_request_id, timeout_seconds=3.0) == (
            IdentityRecoveryCleanupState.CONFIRMED
        )

        assert not await provider.token_is_active(first.access_token)
        assert await provider.refresh_tokens(first) is None
        assert await provider.token_is_active(second.access_token)
        assert await provider.refresh_tokens(second) is not None
        assert await provider.login_can_skip(browser)


@pytest.mark.asyncio
async def test_lost_cleanup_response_can_be_reconciled_without_harming_later_tokens(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
    hydra_sdk: OAuth2Api,
) -> None:
    """Hydra really deletes the grant before the adapter loses its acknowledgement."""
    old = await provider.issue_tokens(alice)
    original = hydra_sdk.revoke_o_auth2_consent_sessions_with_http_info

    def revoke_then_lose_response(**_kwargs: object) -> None:
        response = original(
            consent_request_id=old.consent_request_id.value.hex, _request_timeout=2.0
        )
        assert response.status_code == 204
        raise TimeoutError("Synthetic lost acknowledgement")

    with patch.object(
        hydra_sdk,
        "revoke_o_auth2_consent_sessions_with_http_info",
        side_effect=revoke_then_lose_response,
    ) as revoke:
        assert await revoker.revoke_grant(old.consent_request_id, timeout_seconds=3.0) == (
            IdentityRecoveryCleanupState.UNCERTAIN
        )
    revoke.assert_called_once()
    assert not await provider.token_is_active(old.access_token)
    assert await provider.refresh_tokens(old) is None
    later = await provider.issue_tokens(alice)

    assert await revoker.revoke_grant(old.consent_request_id, timeout_seconds=3.0) == (
        IdentityRecoveryCleanupState.CONFIRMED
    )
    assert await provider.token_is_active(later.access_token)
    assert await provider.refresh_tokens(later) is not None
