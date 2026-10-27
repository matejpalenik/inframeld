"""Show why bulk recovery cleanup must not depend on a consent inventory."""

import os
from collections.abc import AsyncGenerator, Iterator
from dataclasses import replace
from uuid import uuid4

import httpx2
import pytest
import pytest_asyncio
from ory_hydra_client import ApiClient, Configuration, OAuth2Api
from pydantic import BaseModel, ConfigDict, SecretStr, TypeAdapter, ValidationError
from tests.support.hydra_provider import HydraTestProvider, hydra_test_provider
from tests.support.integration_services import HYDRA_ADMIN_URL
from tests.support.kratos_browser import (
    RegisteredHumanDTO,
    create_browser,
    login_human,
    register_human,
)
from tests.support.kratos_recovery import (
    redeem_recovery_code,
    request_recovery_code,
    wait_for_recovery_code,
)
from tests.support.kratos_settings import read_recovery_settings, submit_password_settings

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


class _ConsentSubject(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    subject: str


class _ListedConsent(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    consent_request: _ConsentSubject


@pytest_asyncio.fixture
async def provider() -> AsyncGenerator[HydraTestProvider]:
    async with hydra_test_provider() as provider:
        yield provider


@pytest_asyncio.fixture
async def alice(provider: HydraTestProvider) -> RegisteredHumanDTO:
    async with create_browser() as browser:
        return await register_human(browser)


@pytest.fixture
def revoker() -> Iterator[HydraHumanOAuthCredentialRevoker]:
    sdk = ApiClient(Configuration(host=HYDRA_ADMIN_URL, retries=0, debug=False))
    try:
        yield HydraHumanOAuthCredentialRevoker(OAuth2Api(sdk))
    finally:
        sdk.rest_client.pool_manager.clear()


def _browser() -> httpx2.AsyncClient:
    return httpx2.AsyncClient(timeout=5.0, follow_redirects=False, trust_env=False)


async def _listed_consent_count(subject: IdentitySubject) -> int:
    """Observe one small fixture page - never select cleanup targets from its contents."""
    async with _browser() as client:
        response = await client.get(
            f"{HYDRA_ADMIN_URL}/admin/oauth2/auth/sessions/consent",
            params={"subject": subject.value, "page_size": "10"},
        )
    assert response.status_code == 200, "Could not observe the fixture's consent listing."
    assert "next" not in response.links, "Small fixture unexpectedly requires pagination."
    try:
        rows = TypeAdapter(list[_ListedConsent]).validate_json(response.content)
    except ValidationError:
        raise AssertionError("Could not read the fixture's consent observations.") from None
    assert len(rows) < 10, "Fixture exceeded its single-page bound."
    assert all(row.consent_request.subject == subject.value for row in rows)
    return len(rows)


@pytest.mark.asyncio
async def test_bulk_cleanup_removes_skipped_consent_tokens_missing_from_listing(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
) -> None:
    """The provider can revoke Alice's omitted grant without our application enumerating it."""
    async with _browser() as browser:
        first = await provider.issue_tokens(
            alice, browser=browser, remember_login=True, remember_consent=True
        )
        assert await provider.token_is_active(first.access_token)
        skipped = await provider.issue_tokens(
            alice, browser=browser, remember_login=True, remember_consent=True
        )
        assert not first.consent_skipped
        assert skipped.consent_skipped
        assert await provider.token_is_active(skipped.access_token)
        assert await _listed_consent_count(alice.subject) == 1

        assert (await revoker.revoke_cli_grants(alice.subject, timeout_seconds=3.0)).state == (
            IdentityRecoveryCleanupState.CONFIRMED
        )

        for tokens in (first, skipped):
            assert not await provider.token_is_active(tokens.access_token)
            assert await provider.refresh_tokens(tokens) is None
        assert await _listed_consent_count(alice.subject) == 0
        assert await provider.login_can_skip(browser)


@pytest.mark.asyncio
async def test_bulk_cleanup_forgets_login_without_accepted_consent(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
) -> None:
    """An empty consent listing does not mean Alice has no remembered authentication."""
    async with _browser() as browser:
        await provider.remember_login_without_consent(alice, browser=browser)
        assert await _listed_consent_count(alice.subject) == 0
        assert await provider.login_can_skip(browser)

        assert (
            await revoker.revoke_remembered_logins(alice.subject, timeout_seconds=3.0)
        ).state == (IdentityRecoveryCleanupState.CONFIRMED)
        assert not await provider.login_can_skip(browser)


@pytest.mark.asyncio
async def test_removing_last_visible_grant_still_requires_remembered_login_cleanup(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
) -> None:
    async with _browser() as browser:
        tokens = await provider.issue_tokens(alice, browser=browser, remember_login=True)
        assert await _listed_consent_count(alice.subject) == 1
        assert (await revoker.revoke_cli_grants(alice.subject, timeout_seconds=3.0)).state == (
            IdentityRecoveryCleanupState.CONFIRMED
        )
        assert not await provider.token_is_active(tokens.access_token)
        assert await provider.refresh_tokens(tokens) is None
        assert await _listed_consent_count(alice.subject) == 0
        assert await provider.login_can_skip(browser)

        assert (
            await revoker.revoke_remembered_logins(alice.subject, timeout_seconds=3.0)
        ).state == (IdentityRecoveryCleanupState.CONFIRMED)
        assert not await provider.login_can_skip(browser)


@pytest.mark.asyncio
async def test_unknown_subject_empty_listing_does_not_establish_identity(
    provider: HydraTestProvider,
) -> None:
    assert await _listed_consent_count(IdentitySubject(str(uuid4()))) == 0


@pytest.mark.asyncio
async def test_bulk_cleanup_removes_password_gap_and_later_credentials_but_keeps_recovery_session(
    provider: HydraTestProvider,
    alice: RegisteredHumanDTO,
    revoker: HydraHumanOAuthCredentialRevoker,
) -> None:
    """Kratos password replacement and Hydra cleanup protect different credentials."""
    old = await provider.issue_tokens(alice)
    assert await _listed_consent_count(alice.subject) == 1
    async with create_browser() as recovering, create_browser() as intervening:
        recovery = await request_recovery_code(recovering, alice.email)
        redeemed = await redeem_recovery_code(
            recovering, recovery, await wait_for_recovery_code(alice.email)
        )
        settings = await read_recovery_settings(recovering, redeemed)
        gap_human = replace(alice, credential=await login_human(intervening, alice))
        gap = await provider.issue_tokens(gap_human)
        replacement = SecretStr(f"ReplacementPassphrase-{uuid4().hex}!")
        changed = await submit_password_settings(recovering, settings, replacement)
        assert changed.status_code == 200, "Kratos did not complete password replacement."
        assert (await intervening.get("/sessions/whoami")).status_code == 401
        assert (await recovering.get("/sessions/whoami")).status_code == 200
        assert await provider.token_is_active(old.access_token)
        assert await provider.token_is_active(gap.access_token)
        assert await _listed_consent_count(alice.subject) == 2

        async with create_browser() as legitimate:
            updated = replace(alice, password=replacement.get_secret_value())
            updated = replace(updated, credential=await login_human(legitimate, updated))
            later = await provider.issue_tokens(updated, browser=legitimate, remember_login=True)
            assert await provider.token_is_active(later.access_token)

            assert (await revoker.revoke_cli_grants(alice.subject, timeout_seconds=3.0)).state == (
                IdentityRecoveryCleanupState.CONFIRMED
            )
            assert (
                await revoker.revoke_remembered_logins(alice.subject, timeout_seconds=3.0)
            ).state == (IdentityRecoveryCleanupState.CONFIRMED)

            for tokens in (old, gap, later):
                assert not await provider.token_is_active(tokens.access_token)
                assert await provider.refresh_tokens(tokens) is None
            assert (await recovering.get("/sessions/whoami")).status_code == 200
            assert (await legitimate.get("/sessions/whoami")).status_code == 200
            fresh = await provider.issue_tokens(updated, browser=legitimate, remember_login=True)
            assert await provider.token_is_active(fresh.access_token)
            assert await provider.refresh_tokens(fresh) is not None
