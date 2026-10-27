"""Use production setup against real Hydra, without the helper's registration shortcut."""

import asyncio
import base64
import hashlib
import json
import os
import secrets
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx2
import pytest
from ory_hydra_client import ApiClient, Configuration, OAuth2Api
from ory_hydra_client.exceptions import ApiException
from ory_hydra_client.models.json_patch import JsonPatch
from ory_hydra_client.models.o_auth2_client import OAuth2Client
from pydantic import BaseModel, ConfigDict
from tests.support.hydra_provider import (
    API_AUDIENCE,
    CLIENT_ID,
    HydraTestEndpointsDTO,
    HydraTestProvider,
)
from tests.support.integration_services import (
    EXPIRING_KRATOS_PUBLIC_URL,
    KRATOS_PUBLIC_URL,
    LIFETIME_HYDRA_ADMIN_URL,
    LIFETIME_HYDRA_PUBLIC_URL,
)
from tests.support.kratos_browser import register_human

from inframeld_backend.access.application.enums.human_oauth_client_provisioning_outcome import (
    HumanOAuthClientProvisioningOutcome,
)
from inframeld_backend.access.infrastructure.writers.hydra_human_oauth_client_provisioner import (
    HydraHumanOAuthClientProvisioner,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_HYDRA_INTEGRATION") != "1",
    reason="Requires the private integration services",
)


class _SessionTimes(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    issued_at: datetime
    expires_at: datetime


class _Discovery(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    revocation_endpoint: str
    jwks_uri: str
    code_challenge_methods_supported: list[str]


@dataclass(frozen=True, slots=True)
class ProvisionedProviderScenario:
    sdk: OAuth2Api
    provisioner: HydraHumanOAuthClientProvisioner
    provider: HydraTestProvider
    endpoints: HydraTestEndpointsDTO


def _browser(public_url: str = KRATOS_PUBLIC_URL) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        base_url=public_url, timeout=5, follow_redirects=False, trust_env=False
    )


@asynccontextmanager
async def _provisioned(*, short: bool = False) -> AsyncGenerator[ProvisionedProviderScenario]:
    endpoints = (
        HydraTestEndpointsDTO(LIFETIME_HYDRA_PUBLIC_URL, LIFETIME_HYDRA_ADMIN_URL)
        if short
        else HydraTestEndpointsDTO()
    )
    client = ApiClient(Configuration(host=endpoints.admin_url, retries=0, debug=False))
    sdk = OAuth2Api(client)
    try:
        try:
            await asyncio.to_thread(sdk.delete_o_auth2_client, id=CLIENT_ID, _request_timeout=5)
        except ApiException as error:
            status: object = getattr(error, "status", None)
            if status != 404:
                raise
        provisioner = HydraHumanOAuthClientProvisioner(sdk)
        assert (
            await provisioner.ensure_client(api_audience=API_AUDIENCE, timeout_seconds=5)
            is HumanOAuthClientProvisioningOutcome.CREATED
        )
        async with httpx2.AsyncClient(timeout=5, trust_env=False, follow_redirects=False) as http:
            yield ProvisionedProviderScenario(
                sdk, provisioner, HydraTestProvider(http, endpoints=endpoints), endpoints
            )
    finally:
        try:
            await asyncio.to_thread(sdk.delete_o_auth2_client, id=CLIENT_ID, _request_timeout=5)
        finally:
            client.rest_client.pool_manager.clear()


@pytest.mark.asyncio
async def test_setup_reconciliation_preserves_logins_and_unrelated_client_metadata() -> None:
    """Repair the official profile in place while Alice and Bob retain their live chains."""
    async with (
        asyncio.timeout(30),
        _provisioned() as scenario,
        _browser() as alice_browser,
        _browser() as bob_browser,
    ):
        alice, bob = await register_human(alice_browser), await register_human(bob_browser)
        alices = await scenario.provider.issue_tokens(
            alice, browser=alice_browser, remember_login=True
        )
        bobs = await scenario.provider.issue_tokens(bob, browser=bob_browser, remember_login=True)
        other_id = f"other-{uuid4()}"
        await asyncio.to_thread(
            scenario.sdk.create_o_auth2_client,
            o_auth2_client=OAuth2Client(
                client_id=other_id,
                client_name="Keep this client",
                token_endpoint_auth_method="none",
            ),
            _request_timeout=5,
        )
        try:
            assert (
                await scenario.provisioner.ensure_client(
                    api_audience=API_AUDIENCE, timeout_seconds=5
                )
                is HumanOAuthClientProvisioningOutcome.UNCHANGED
            )
            await asyncio.to_thread(
                scenario.sdk.patch_o_auth2_client,
                id=CLIENT_ID,
                json_patch=[
                    JsonPatch(op="add", path="/skip_consent", value=True),
                    JsonPatch(
                        op="add", path="/authorization_code_grant_access_token_lifespan", value="3h"
                    ),
                    JsonPatch(op="add", path="/metadata", value={"operator": "keep"}),
                ],
                _request_timeout=5,
            )
            assert (
                await scenario.provisioner.ensure_client(
                    api_audience=API_AUDIENCE, timeout_seconds=5
                )
                is HumanOAuthClientProvisioningOutcome.UPDATED
            )
            current = await asyncio.to_thread(
                scenario.sdk.get_o_auth2_client, id=CLIENT_ID, _request_timeout=5
            )
            assert current.metadata == {"operator": "keep"}
            assert current.authorization_code_grant_access_token_lifespan is None
            other = await asyncio.to_thread(
                scenario.sdk.get_o_auth2_client, id=other_id, _request_timeout=5
            )
            assert other.client_name == "Keep this client"
            for tokens in (alices, bobs):
                assert await scenario.provider.token_is_active(tokens.access_token)
                assert await scenario.provider.refresh_tokens(tokens) is not None
            assert await scenario.provider.login_can_skip(alice_browser)
            assert await scenario.provider.login_can_skip(bob_browser)
        finally:
            await asyncio.to_thread(
                scenario.sdk.delete_o_auth2_client, id=other_id, _request_timeout=5
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("port", [49152, 52731])
async def test_registered_loopback_callback_accepts_the_cli_chosen_port(port: int) -> None:
    async with (
        asyncio.timeout(30),
        _provisioned() as scenario,
        _browser() as browser,
        httpx2.AsyncClient(timeout=5, trust_env=False) as http,
    ):
        alice = await register_human(browser)
        provider = HydraTestProvider(
            http,
            endpoints=scenario.endpoints,
            redirect_uri=f"http://127.0.0.1:{port}/oauth/callback",
        )
        tokens = await provider.issue_tokens(alice)
        assert await provider.token_is_active(tokens.access_token)


@pytest.mark.asyncio
async def test_exchange_requires_the_same_callback_used_for_authorization() -> None:
    async with asyncio.timeout(30), _provisioned() as scenario, _browser() as browser:
        alice = await register_human(browser)
        code = await scenario.provider.approve_login_and_consent(
            await scenario.provider.begin_login(alice)
        )
        assert (
            await scenario.provider.exchange_authorization_code(
                code, redirect_uri="http://127.0.0.1:52731/oauth/callback"
            )
            is None
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "redirect",
    [
        "http://localhost:49152/oauth/callback",
        "http://127.0.0.2:49152/oauth/callback",
        "http://[::1]:49152/oauth/callback",
        "http://127.0.0.1:49152/wrong",
        "https://outside.test/oauth/callback",
        "http://127.0.0.1:49152/oauth/callback?extra=1",
        "http://127.0.0.1:49152/oauth/callback#fragment",
        "https://127.0.0.1:49152/oauth/callback",
    ],
)
async def test_registration_rejects_unsupported_callback_hosts_and_paths(redirect: str) -> None:
    async with (
        asyncio.timeout(30),
        _provisioned() as scenario,
        httpx2.AsyncClient(timeout=5, trust_env=False, follow_redirects=False) as http,
    ):
        verifier = secrets.token_urlsafe(48)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        response = await http.get(
            f"{scenario.endpoints.public_url}/oauth2/auth",
            params={
                "client_id": CLIENT_ID,
                "redirect_uri": redirect,
                "response_type": "code",
                "scope": "inframeld:api offline_access",
                "audience": API_AUDIENCE.value,
                "state": secrets.token_urlsafe(32),
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        location = urlsplit(response.headers.get("location", ""))
        assert response.status_code == 302
        assert f"{location.scheme}://{location.netloc}" == scenario.endpoints.public_url
        assert location.path == "/oauth2/fallbacks/error"
        assert parse_qs(location.query).get("error") == ["invalid_request"]
        assert "code" not in parse_qs(location.query)


@pytest.mark.asyncio
@pytest.mark.parametrize("short", [False, True])
async def test_native_lifetimes_apply_to_issuance_and_rolling_refresh(short: bool) -> None:
    async with asyncio.timeout(30), _provisioned(short=short) as scenario, _browser() as browser:
        alice = await register_human(browser)
        tokens = await scenario.provider.issue_tokens(alice)
        access = await asyncio.to_thread(
            scenario.sdk.introspect_o_auth2_token,
            token=tokens.access_token.value,
            _request_timeout=5,
        )
        refresh = await asyncio.to_thread(
            scenario.sdk.introspect_o_auth2_token,
            token=tokens.refresh_token.get_secret_value(),
            _request_timeout=5,
        )
        assert access.exp is not None and access.iat is not None
        assert refresh.exp is not None and refresh.iat is not None
        assert abs(access.exp - access.iat - (30 if short else 300)) <= 2
        assert abs(refresh.exp - refresh.iat - (120 if short else 604800)) <= 2
        # Let the provider's whole-second clock advance, not a concurrent request ordering.
        await asyncio.sleep(1.1)
        renewed = await scenario.provider.refresh_tokens(tokens)
        assert renewed is not None
        next_refresh = await asyncio.to_thread(
            scenario.sdk.introspect_o_auth2_token,
            token=renewed.refresh_token.get_secret_value(),
            _request_timeout=5,
        )
        assert next_refresh.exp is not None and next_refresh.iat is not None
        assert next_refresh.exp > refresh.exp
        assert abs(next_refresh.exp - next_refresh.iat - (120 if short else 604800)) <= 2
        next_access = await asyncio.to_thread(
            scenario.sdk.introspect_o_auth2_token,
            token=renewed.access_token.value,
            _request_timeout=5,
        )
        assert next_access.exp is not None and next_access.iat is not None
        assert abs(next_access.exp - next_access.iat - (30 if short else 300)) <= 2


@pytest.mark.asyncio
async def test_standard_discovery_names_the_exact_provider_and_cli_endpoints() -> None:
    async with (
        asyncio.timeout(30),
        _provisioned() as scenario,
        httpx2.AsyncClient(timeout=5, trust_env=False) as http,
    ):
        response = await http.get(
            f"{scenario.endpoints.public_url}/.well-known/openid-configuration"
        )
        assert response.status_code == 200
        metadata = _Discovery.model_validate_json(response.text)
        assert metadata.issuer == f"{scenario.endpoints.public_url}/"
        assert metadata.authorization_endpoint == f"{scenario.endpoints.public_url}/oauth2/auth"
        assert metadata.token_endpoint == f"{scenario.endpoints.public_url}/oauth2/token"
        assert metadata.revocation_endpoint == f"{scenario.endpoints.public_url}/oauth2/revoke"
        assert metadata.jwks_uri == f"{scenario.endpoints.public_url}/.well-known/jwks.json"
        assert "S256" in metadata.code_challenge_methods_supported


@pytest.mark.asyncio
async def test_native_code_lifetime_override_rejects_an_expired_code_with_a_default_control() -> (
    None
):
    async with (
        asyncio.timeout(30),
        _provisioned() as normal,
        _provisioned(short=True) as short,
        _browser() as browser,
    ):
        alice = await register_human(browser)
        normal_code = await normal.provider.approve_login_and_consent(
            await normal.provider.begin_login(alice)
        )
        short_code = await short.provider.approve_login_and_consent(
            await short.provider.begin_login(alice)
        )
        await asyncio.sleep(6)
        assert await short.provider.exchange_authorization_code(short_code) is None
        assert await normal.provider.exchange_authorization_code(normal_code) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "expected_seconds"), [(KRATOS_PUBLIC_URL, 28800), (EXPIRING_KRATOS_PUBLIC_URL, 15)]
)
async def test_native_kratos_session_lifetime_is_effective(url: str, expected_seconds: int) -> None:
    async with asyncio.timeout(30), _browser(url) as browser:
        await register_human(browser)
        response = await browser.get("/sessions/whoami")
        assert response.status_code == 200
        times = _SessionTimes.model_validate_json(response.text)
        assert abs((times.expires_at - times.issued_at).total_seconds() - expected_seconds) <= 2


@pytest.mark.asyncio
async def test_real_setup_command_is_repeatable_without_application_configuration() -> None:
    async with asyncio.timeout(30), _provisioned() as scenario:
        environment = {
            key: value for key, value in os.environ.items() if not key.startswith("INFRAMELD_")
        }
        environment.update(
            {
                "INFRAMELD_HYDRA__ADMIN_URL": scenario.endpoints.admin_url,
                "INFRAMELD_HYDRA__ISSUER": f"{scenario.endpoints.public_url}/",
                "INFRAMELD_HYDRA__API_AUDIENCE": API_AUDIENCE.value,
            }
        )
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "inframeld_backend.provision_oauth_client",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
        )
        try:
            stdout, stderr = await process.communicate()
            assert process.returncode == 0
            assert stderr == b""
            assert json.loads(stdout) == {"clientId": CLIENT_ID, "outcome": "unchanged"}
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
