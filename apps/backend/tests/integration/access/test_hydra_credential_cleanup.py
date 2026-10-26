"""Qualify bulk recovery cleanup against the pinned real Hydra server."""

import os
from collections.abc import AsyncGenerator, Iterator
from typing import Literal
from unittest.mock import patch
from uuid import uuid4

import httpx2
import pytest
import pytest_asyncio
from ory_hydra_client import ApiClient, Configuration, OAuth2Api
from tests.support.hydra_provider import CLIENT_ID, HydraTestProvider, hydra_test_provider
from tests.support.integration_services import HYDRA_ADMIN_URL
from tests.support.kratos_browser import RegisteredHumanDTO, create_browser, register_human

from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.revokers.hydra_human_oauth_credential_revoker import (
    HydraHumanOAuthCredentialRevoker,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_HYDRA_INTEGRATION") != "1",
    reason="Requires the private integration services",
)

type Operation = Literal["grant", "login"]


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


async def _revoke(
    revoker: HydraHumanOAuthCredentialRevoker, operation: Operation, subject: IdentitySubject
) -> IdentityRecoveryCleanupState:
    if operation == "grant":
        return (await revoker.revoke_cli_grants(subject, timeout_seconds=3.0)).state
    return (await revoker.revoke_remembered_logins(subject, timeout_seconds=3.0)).state


@pytest.mark.asyncio
async def test_bulk_grants_remove_every_alice_cli_chain_and_preserve_bob(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
) -> None:
    """One subject/client call covers independent logins and rotated refresh descendants."""
    async with create_browser() as registration:
        bob = await register_human(registration)
    async with _browser() as first_browser, _browser() as other_browser, _browser() as bob_browser:
        first = await provider.issue_tokens(alice, browser=first_browser, remember_login=True)
        same_login = await provider.issue_tokens(alice, browser=first_browser, remember_login=True)
        other = await provider.issue_tokens(alice, browser=other_browser, remember_login=True)
        bobs = await provider.issue_tokens(bob, browser=bob_browser, remember_login=True)
        refreshed = await provider.refresh_tokens(first)
        assert refreshed is not None
        alices = (first, same_login, other, refreshed)
        # Refresh may invalidate the original access token. Check the live chains.
        for tokens in (same_login, other, refreshed):
            assert await provider.token_is_active(tokens.access_token)

        assert (await revoker.revoke_cli_grants(alice.subject, timeout_seconds=3.0)).state == (
            IdentityRecoveryCleanupState.CONFIRMED
        )

        for tokens in alices:
            assert not await provider.token_is_active(tokens.access_token)
            assert await provider.refresh_tokens(tokens) is None
        assert await provider.login_can_skip(first_browser)
        assert await provider.login_can_skip(other_browser)
        assert await provider.token_is_active(bobs.access_token)
        assert await provider.refresh_tokens(bobs) is not None
        assert await provider.login_can_skip(bob_browser)


@pytest.mark.asyncio
async def test_bulk_login_cleanup_forgets_alices_browsers_but_keeps_tokens_and_bob(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
) -> None:
    """Forgetting remembered authentication does not invalidate issued token grants."""
    async with create_browser() as registration:
        bob = await register_human(registration)
    async with _browser() as first_browser, _browser() as other_browser, _browser() as bob_browser:
        first = await provider.issue_tokens(alice, browser=first_browser, remember_login=True)
        other = await provider.issue_tokens(alice, browser=other_browser, remember_login=True)
        bobs = await provider.issue_tokens(bob, browser=bob_browser, remember_login=True)
        assert await provider.login_can_skip(first_browser)
        assert await provider.login_can_skip(other_browser)

        assert (
            await revoker.revoke_remembered_logins(alice.subject, timeout_seconds=3.0)
        ).state == (IdentityRecoveryCleanupState.CONFIRMED)

        assert not await provider.login_can_skip(first_browser)
        assert not await provider.login_can_skip(other_browser)
        for tokens in (first, other, bobs):
            assert await provider.token_is_active(tokens.access_token)
            assert await provider.refresh_tokens(tokens) is not None
        assert await provider.login_can_skip(bob_browser)


@pytest.mark.asyncio
async def test_cli_grant_cleanup_preserves_alices_grants_for_another_client(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
) -> None:
    """Bulk recovery never substitutes deletion for every user of the CLI or every client."""
    cli = await provider.issue_tokens(alice)
    async with hydra_test_provider(client_id="inframeld-test-other-client") as other_provider:
        other = await other_provider.issue_tokens(alice)

        assert (await revoker.revoke_cli_grants(alice.subject, timeout_seconds=3.0)).state == (
            IdentityRecoveryCleanupState.CONFIRMED
        )

        assert not await provider.token_is_active(cli.access_token)
        assert await provider.refresh_tokens(cli) is None
        assert await other_provider.token_is_active(other.access_token)
        assert await other_provider.refresh_tokens(other) is not None


@pytest.mark.asyncio
async def test_bulk_remembered_login_cleanup_applies_across_clients(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
) -> None:
    """Hydra's subject-wide remembered-login operation has no client filter."""
    async with (
        hydra_test_provider(client_id="inframeld-test-other-client") as other_provider,
        _browser() as cli_browser,
        _browser() as other_browser,
    ):
        cli = await provider.issue_tokens(alice, browser=cli_browser, remember_login=True)
        other = await other_provider.issue_tokens(alice, browser=other_browser, remember_login=True)
        assert await provider.login_can_skip(cli_browser)
        assert await other_provider.login_can_skip(other_browser)

        assert (
            await revoker.revoke_remembered_logins(alice.subject, timeout_seconds=3.0)
        ).state == (IdentityRecoveryCleanupState.CONFIRMED)

        assert not await provider.login_can_skip(cli_browser)
        assert not await other_provider.login_can_skip(other_browser)
        assert await provider.token_is_active(cli.access_token)
        assert await provider.refresh_tokens(cli) is not None
        assert await other_provider.token_is_active(other.access_token)
        assert await other_provider.refresh_tokens(other) is not None


@pytest.mark.asyncio
async def test_repeating_bulk_cleanup_can_revoke_alices_newer_login(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
) -> None:
    """An unfinished cleanup may be retried broadly, then Alice can authenticate again."""
    async with _browser() as browser:
        old = await provider.issue_tokens(alice, browser=browser, remember_login=True)
        for operation in ("grant", "login"):
            assert await _revoke(revoker, operation, alice.subject) == (
                IdentityRecoveryCleanupState.CONFIRMED
            )
        assert not await provider.token_is_active(old.access_token)
        assert await provider.refresh_tokens(old) is None
        assert not await provider.login_can_skip(browser)
        later = await provider.issue_tokens(alice, browser=browser, remember_login=True)
        assert await provider.token_is_active(later.access_token)
        assert await provider.login_can_skip(browser)

        for operation in ("grant", "login"):
            assert await _revoke(revoker, operation, alice.subject) == (
                IdentityRecoveryCleanupState.CONFIRMED
            )

        assert not await provider.token_is_active(later.access_token)
        assert await provider.refresh_tokens(later) is None
        assert not await provider.login_can_skip(browser)
        fresh = await provider.issue_tokens(alice, browser=browser, remember_login=True)
        assert await provider.token_is_active(fresh.access_token)
        assert await provider.refresh_tokens(fresh) is not None
        assert await provider.login_can_skip(browser)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["grant", "login"])
async def test_empty_bulk_scope_is_acknowledged_without_affecting_existing_credentials(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
    operation: Operation,
) -> None:
    """A missing subject's 204 confirms only the empty request, not that an account exists."""
    existing = await provider.issue_tokens(alice)
    missing = IdentitySubject(str(uuid4()))
    for _repeat in range(2):
        assert await _revoke(revoker, operation, missing) == IdentityRecoveryCleanupState.CONFIRMED
    assert await provider.token_is_active(existing.access_token)
    assert await provider.refresh_tokens(existing) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["grant", "login"])
async def test_lost_bulk_response_retry_can_remove_newer_alice_credentials(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
    hydra_sdk: OAuth2Api,
    operation: Operation,
) -> None:
    """Hydra really completes cleanup before a synthetic acknowledgement loss and retry."""
    async with create_browser() as registration:
        bob = await register_human(registration)
    bobs = await provider.issue_tokens(bob)
    original_grants = hydra_sdk.revoke_o_auth2_consent_sessions_with_http_info
    original_logins = hydra_sdk.revoke_o_auth2_login_sessions_with_http_info

    def revoke_then_lose_response(**_kwargs: object) -> None:
        if operation == "grant":
            response = original_grants(
                subject=alice.subject.value, client=CLIENT_ID, _request_timeout=2.0
            )
        else:
            response = original_logins(subject=alice.subject.value, _request_timeout=2.0)
        assert response.status_code == 204
        raise TimeoutError("Synthetic lost acknowledgement")

    method = (
        "revoke_o_auth2_consent_sessions_with_http_info"
        if operation == "grant"
        else "revoke_o_auth2_login_sessions_with_http_info"
    )
    async with _browser() as browser:
        old = await provider.issue_tokens(alice, browser=browser, remember_login=True)
        with patch.object(hydra_sdk, method, side_effect=revoke_then_lose_response) as revoke:
            assert await _revoke(revoker, operation, alice.subject) == (
                IdentityRecoveryCleanupState.UNCERTAIN
            )
        revoke.assert_called_once()
        if operation == "grant":
            assert not await provider.token_is_active(old.access_token)
            assert await provider.refresh_tokens(old) is None
        else:
            assert not await provider.login_can_skip(browser)

        later = await provider.issue_tokens(alice, browser=browser, remember_login=True)
        assert await provider.token_is_active(later.access_token)
        assert await provider.login_can_skip(browser)
        assert await _revoke(revoker, operation, alice.subject) == (
            IdentityRecoveryCleanupState.CONFIRMED
        )

        if operation == "grant":
            assert not await provider.token_is_active(later.access_token)
            assert await provider.refresh_tokens(later) is None
            assert await provider.login_can_skip(browser)
        else:
            assert not await provider.login_can_skip(browser)
            assert await provider.token_is_active(later.access_token)
            assert await provider.refresh_tokens(later) is not None
        assert await provider.token_is_active(bobs.access_token)
        assert await provider.refresh_tokens(bobs) is not None


@pytest.mark.asyncio
async def test_non_remembered_reauthentication_recovers_after_revoked_cookie_rejection(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
) -> None:
    """Pinned Hydra clears a stale remembered cookie on rejection before a new attempt works."""
    async with _browser() as browser:
        old = await provider.issue_tokens(alice, browser=browser, remember_login=True)
        assert (
            await revoker.revoke_remembered_logins(alice.subject, timeout_seconds=3.0)
        ).state == (IdentityRecoveryCleanupState.CONFIRMED)
        with pytest.raises(
            AssertionError,
            match=r"^Hydra rejected OAuth authorization with error category 'error'\.$",
        ):
            await provider.issue_tokens(alice, browser=browser, remember_login=False)

        # This is an explicit second user attempt, not a hidden helper retry.
        fresh = await provider.issue_tokens(alice, browser=browser, remember_login=False)
        assert await provider.token_is_active(old.access_token)
        assert await provider.token_is_active(fresh.access_token)
        assert await provider.refresh_tokens(fresh) is not None
        assert not await provider.login_can_skip(browser)
