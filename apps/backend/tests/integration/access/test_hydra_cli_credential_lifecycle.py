"""Qualify CLI proof, renewal and selected-login logout against real Hydra."""

import asyncio
import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass, replace
from typing import Literal
from uuid import uuid4

import httpx2
import pytest
import pytest_asyncio
from pydantic import SecretStr
from tests.support.hydra_provider import (
    HydraAuthorizationRejectedError,
    HydraTestProvider,
    IssuedHydraTokensDTO,
    PKCEChallenge,
    hydra_test_provider,
)
from tests.support.hydra_token_request_gate import HydraTokenRequestGate
from tests.support.integration_services import KRATOS_PUBLIC_URL
from tests.support.kratos_browser import RegisteredHumanDTO, WhoamiResponse, register_human

from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_HYDRA_INTEGRATION") != "1",
    reason="Requires the private integration services",
)


@dataclass(frozen=True, slots=True)
class CLICredentialScenario:
    provider: HydraTestProvider
    gate: HydraTokenRequestGate
    alice: RegisteredHumanDTO
    binding: HumanOAuthCredentialBindingDTO
    alice_browser: httpx2.AsyncClient
    laptop_browser: httpx2.AsyncClient
    desktop_browser: httpx2.AsyncClient


def _browser() -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        base_url=KRATOS_PUBLIC_URL, timeout=5.0, follow_redirects=False, trust_env=False
    )


@pytest_asyncio.fixture
async def scenario() -> AsyncGenerator[CLICredentialScenario]:
    gate = HydraTokenRequestGate(httpx2.AsyncHTTPTransport(retries=0, trust_env=False))
    try:
        async with (
            asyncio.timeout(30.0),
            hydra_test_provider(transport=gate) as provider,
            _browser() as alice_browser,
            _browser() as laptop_browser,
            _browser() as desktop_browser,
        ):
            alice = await register_human(alice_browser)
            # Trusted fixture metadata qualifies Hydra preservation, not local admission.
            binding = HumanOAuthCredentialBindingDTO(
                VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), alice.subject),
                InstallationId(uuid4()),
                HumanCredentialVersion(6),
            )
            yield CLICredentialScenario(
                provider, gate, alice, binding, alice_browser, laptop_browser, desktop_browser
            )
    finally:
        await gate.aclose()


async def _assert_revoked(provider: HydraTestProvider, tokens: IssuedHydraTokensDTO) -> None:
    assert not await provider.token_is_active(tokens.access_token)
    assert await provider.refresh_tokens(tokens) is None


async def _assert_renewable(provider: HydraTestProvider, tokens: IssuedHydraTokensDTO) -> None:
    assert await provider.token_is_active(tokens.access_token)
    renewed = await provider.refresh_tokens(tokens)
    assert renewed is not None
    assert await provider.token_is_active(renewed.access_token)


async def _assert_browser_still_signed_in(scenario: CLICredentialScenario) -> None:
    response = await scenario.alice_browser.get("/sessions/whoami")
    assert response.status_code == 200
    assert str(WhoamiResponse.model_validate_json(response.text).identity.id) == (
        scenario.alice.subject.value
    )
    assert await scenario.provider.login_can_skip(scenario.laptop_browser)


@pytest.mark.asyncio
async def test_s256_code_exchange_preserves_the_bound_human_and_installation(
    scenario: CLICredentialScenario,
) -> None:
    code = await scenario.provider.approve_login_and_consent(
        await scenario.provider.begin_login(scenario.alice), credential_binding=scenario.binding
    )
    tokens = await scenario.provider.exchange_authorization_code(code)
    assert tokens is not None
    await scenario.provider.assert_token_binding(tokens.access_token, binding=scenario.binding)


@pytest.mark.asyncio
@pytest.mark.parametrize("pkce", ["missing", "plain", "missing_method"])
async def test_invalid_pkce_authorization_is_rejected_by_hydra(
    scenario: CLICredentialScenario, pkce: PKCEChallenge
) -> None:
    """A public CLI cannot obtain a code without an explicitly supported S256 challenge."""
    with pytest.raises(HydraAuthorizationRejectedError) as failure:
        pending = await scenario.provider.begin_login(scenario.alice, pkce=pkce)
        await scenario.provider.approve_login_and_consent(pending)
    assert failure.value.error == "invalid_request"


@pytest.mark.asyncio
@pytest.mark.parametrize("proof", ["missing", "incorrect", "another_flow"])
async def test_code_exchange_rejects_missing_incorrect_or_other_flow_proof(
    scenario: CLICredentialScenario, proof: Literal["missing", "incorrect", "another_flow"]
) -> None:
    code = await scenario.provider.approve_login_and_consent(
        await scenario.provider.begin_login(scenario.alice)
    )
    if proof == "incorrect":
        code = replace(code, verifier=SecretStr("W" * 64))
    elif proof == "another_flow":
        other = await scenario.provider.begin_login(scenario.alice)
        code = replace(code, verifier=other.verifier)
    assert (
        await scenario.provider.exchange_authorization_code(code, omit_verifier=proof == "missing")
        is None
    )


@pytest.mark.asyncio
async def test_reusing_a_code_is_denied_and_revokes_its_issued_credentials(
    scenario: CLICredentialScenario,
) -> None:
    """An ambiguously consumed code must not be replayed to recover a lost response."""
    code = await scenario.provider.approve_login_and_consent(
        await scenario.provider.begin_login(scenario.alice)
    )
    tokens = await scenario.provider.exchange_authorization_code(code)
    assert tokens is not None
    assert await scenario.provider.token_is_active(tokens.access_token)
    assert await scenario.provider.exchange_authorization_code(code) is None
    await _assert_revoked(scenario.provider, tokens)


@pytest.mark.asyncio
async def test_legitimate_refresh_rotates_both_secrets_and_preserves_binding(
    scenario: CLICredentialScenario,
) -> None:
    """Alice can renew repeatedly using each replacement, without replaying an old token."""
    current = await scenario.provider.issue_tokens(
        scenario.alice, credential_binding=scenario.binding
    )
    for _ in range(2):
        renewed = await scenario.provider.refresh_tokens(current)
        assert renewed is not None
        assert renewed.access_token != current.access_token
        assert renewed.refresh_token != current.refresh_token
        assert not await scenario.provider.token_is_active(current.access_token)
        await scenario.provider.assert_token_binding(renewed.access_token, binding=scenario.binding)
        current = renewed


@pytest.mark.asyncio
async def test_refresh_reuse_revokes_only_the_affected_login_chain(
    scenario: CLICredentialScenario,
) -> None:
    """Replaying the laptop's old refresh token must not log out Alice's desktop or Bob."""
    async with _browser() as bob_browser:
        bob = await register_human(bob_browser)
        bobs = await scenario.provider.issue_tokens(bob, browser=bob_browser, remember_login=True)
        desktop = await scenario.provider.issue_tokens(
            scenario.alice, browser=scenario.desktop_browser, remember_login=True
        )
        laptop = await scenario.provider.issue_tokens(
            scenario.alice, browser=scenario.laptop_browser, remember_login=True
        )
        renewed = await scenario.provider.refresh_tokens(laptop)
        assert renewed is not None
        assert await scenario.provider.token_is_active(renewed.access_token)
        assert await scenario.provider.refresh_tokens(laptop) is None
        await _assert_revoked(scenario.provider, renewed)
        await _assert_renewable(scenario.provider, desktop)
        await _assert_renewable(scenario.provider, bobs)
        await _assert_browser_still_signed_in(scenario)


@pytest.mark.asyncio
async def test_lost_successful_refresh_response_requires_a_fresh_login(
    scenario: CLICredentialScenario,
) -> None:
    """Cancel delivery after real rotation, then probe reuse explicitly rather than retrying."""
    desktop = await scenario.provider.issue_tokens(
        scenario.alice, browser=scenario.desktop_browser, remember_login=True
    )
    original = await scenario.provider.issue_tokens(
        scenario.alice, browser=scenario.laptop_browser, remember_login=True
    )
    scenario.gate.arm("after_response")
    refresh = asyncio.create_task(scenario.provider.refresh_tokens(original))
    try:
        await scenario.gate.wait_until_paused()
        assert scenario.gate.response_status == 200
        assert not refresh.done()
        assert not await scenario.provider.token_is_active(original.access_token)
        refresh.cancel()
        with pytest.raises(asyncio.CancelledError):
            await refresh
    finally:
        if not refresh.done():
            refresh.cancel()
        await asyncio.gather(refresh, return_exceptions=True)
    # This is a deliberate replay probe, never the helper's recovery strategy.
    assert await scenario.provider.refresh_tokens(original) is None
    fresh = await scenario.provider.issue_tokens(
        scenario.alice, browser=scenario.laptop_browser, remember_login=True
    )
    await _assert_renewable(scenario.provider, fresh)
    await _assert_renewable(scenario.provider, desktop)
    await _assert_browser_still_signed_in(scenario)


@pytest.mark.asyncio
@pytest.mark.parametrize("remembered", [False, True])
async def test_selected_logout_preserves_independent_logins_and_browser_sessions(
    scenario: CLICredentialScenario, remembered: bool
) -> None:
    """Even a remembered-consent grant remains separate from other devices and clients."""
    async with (
        _browser() as bob_browser,
        hydra_test_provider(client_id="inframeld-other-client") as other_client,
    ):
        bob = await register_human(bob_browser)
        bobs = await scenario.provider.issue_tokens(bob, browser=bob_browser, remember_login=True)
        desktop = await scenario.provider.issue_tokens(
            scenario.alice, browser=scenario.desktop_browser, remember_login=True
        )
        other = await other_client.issue_tokens(scenario.alice)
        protected: list[IssuedHydraTokensDTO] = []
        if remembered:
            protected.append(
                await scenario.provider.issue_tokens(
                    scenario.alice,
                    browser=scenario.laptop_browser,
                    remember_login=True,
                    remember_consent=True,
                )
            )
        laptop = await scenario.provider.issue_tokens(
            scenario.alice,
            browser=scenario.laptop_browser,
            remember_login=True,
            remember_consent=remembered,
        )
        assert laptop.consent_skipped is remembered
        renewed = await scenario.provider.refresh_tokens(laptop)
        assert renewed is not None
        assert await scenario.provider.token_is_active(renewed.access_token)
        await scenario.provider.revoke_refresh_token(renewed.refresh_token)
        await _assert_revoked(scenario.provider, renewed)
        await scenario.provider.revoke_refresh_token(renewed.refresh_token)
        await _assert_revoked(scenario.provider, renewed)
        await _assert_revoked(scenario.provider, laptop)
        for tokens in (*protected, desktop, bobs):
            await _assert_renewable(scenario.provider, tokens)
        await _assert_renewable(other_client, other)
        await _assert_browser_still_signed_in(scenario)
        assert await scenario.provider.login_can_skip(scenario.desktop_browser)
        assert await scenario.provider.login_can_skip(bob_browser)
