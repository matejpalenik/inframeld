import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from json import JSONDecodeError
from threading import Event
from typing import Literal
from unittest.mock import patch
from uuid import UUID

import pytest
from ory_hydra_client.api.o_auth2_api import OAuth2Api
from ory_hydra_client.api_client import ApiClient
from ory_hydra_client.configuration import Configuration
from ory_hydra_client.exceptions import ApiException
from ory_hydra_client.models.introspected_o_auth2_token import IntrospectedOAuth2Token
from pydantic import HttpUrl, ValidationError
from urllib3.exceptions import HTTPError

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.oauth_issuer import OAuthIssuer
from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
from inframeld_backend.access.infrastructure.verifiers.hydra_access_token_verifier import (
    HydraAccessTokenVerifier,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)

type RequiredTokenField = Literal[
    "iss", "client_id", "aud", "scope", "exp", "sub", "token_type", "token_use"
]

SETTINGS = HydraSettings(
    admin_url=HttpUrl("http://hydra-admin.test:4445"),
    issuer=OAuthIssuer("https://login.example.test/"),
    api_audience=HumanAPIAudience("https://api.example.test"),
)
AUTHORITY = IdentityAuthority("kratos:test")
IDENTITY_ID = UUID("00000000-0000-4000-8000-000000000003")
CREDENTIAL = HumanAccessTokenCredential("synthetic-human-token")


@pytest.fixture
def client() -> Iterator[OAuth2Api]:
    configuration = Configuration(
        host=str(SETTINGS.admin_url).rstrip("/"),
        retries=0,
        debug=False,
    )
    sdk_client = ApiClient(configuration)

    try:
        yield OAuth2Api(sdk_client)
    finally:
        # This SDK release's context manager does not clear the HTTP pool.
        sdk_client.rest_client.pool_manager.clear()


def _token() -> IntrospectedOAuth2Token:
    now = int(datetime.now(UTC).timestamp())

    return IntrospectedOAuth2Token(
        active=True,
        iss=SETTINGS.issuer.value,
        client_id=SETTINGS.client_id,
        aud=[SETTINGS.api_audience.value],
        scope="openid offline_access inframeld:api",
        exp=now + 300,
        iat=now - 10,
        nbf=now - 10,
        sub=str(IDENTITY_ID),
        token_type="Bearer",
        token_use="access_token",
        username="alice@example.test",
    )


@pytest.mark.asyncio
async def test_valid_access_token_returns_the_existing_kratos_identity(
    client: OAuth2Api,
) -> None:
    verifier = HydraAccessTokenVerifier(client, SETTINGS, AUTHORITY)

    with patch.object(client, "introspect_o_auth2_token", return_value=_token()) as introspect:
        result = await verifier.verify(CREDENTIAL, timeout_seconds=2.0)

    assert result == VerifiedHumanIdentityDTO(
        authority=AUTHORITY,
        subject=IdentitySubject(str(IDENTITY_ID)),
    )
    introspect.assert_called_once()
    assert introspect.call_args.kwargs["token"] == CREDENTIAL.value
    assert introspect.call_args.kwargs["scope"] == "inframeld:api"

    request_timeout: object = introspect.call_args.kwargs["_request_timeout"]
    assert isinstance(request_timeout, float)
    assert 0 < request_timeout <= 2.0


@pytest.mark.asyncio
async def test_inactive_response_needs_no_additional_claims(client: OAuth2Api) -> None:
    with patch.object(
        client,
        "introspect_o_auth2_token",
        return_value=IntrospectedOAuth2Token(active=False),
    ):
        result = await HydraAccessTokenVerifier(client, SETTINGS, AUTHORITY).verify(
            CREDENTIAL,
            timeout_seconds=2.0,
        )

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "updates",
    [
        pytest.param({"iss": "https://other.example.test/"}, id="wrong-issuer"),
        pytest.param({"iss": "https://login.example.test"}, id="issuer-slash-differs"),
        pytest.param({"client_id": "another-client"}, id="wrong-client"),
        pytest.param({"aud": ["https://other-api.example.test"]}, id="wrong-audience"),
        pytest.param({"aud": ["https://api.example.test/"]}, id="audience-slash-differs"),
        pytest.param({"aud": []}, id="no-audience-granted"),
        pytest.param({"scope": "openid offline_access"}, id="missing-api-scope"),
        pytest.param({"scope": "inframeld:api-extra"}, id="scope-prefix-is-insufficient"),
        pytest.param({"token_use": "refresh_token"}, id="refresh-token"),
        pytest.param({"token_use": "id_token"}, id="wrong-token-use"),
        pytest.param({"token_type": "MAC"}, id="wrong-token-type"),
        pytest.param({"exp": 0}, id="expired"),
        pytest.param({"nbf": 4_102_444_800}, id="not-yet-valid"),
        pytest.param({"iat": 4_102_444_800}, id="future-issuance"),
        pytest.param({"obfuscated_subject": "pairwise-subject"}, id="pairwise-mapping"),
    ],
)
async def test_unusable_token_returns_no_identity(
    client: OAuth2Api,
    updates: dict[str, object],
) -> None:
    # These dictionaries describe SDK fields at the provider boundary.
    token = _token().model_copy(update=updates)

    with patch.object(client, "introspect_o_auth2_token", return_value=token):
        result = await HydraAccessTokenVerifier(client, SETTINGS, AUTHORITY).verify(
            CREDENTIAL,
            timeout_seconds=2.0,
        )

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    ["iss", "client_id", "aud", "scope", "exp", "sub", "token_type", "token_use"],
)
async def test_active_response_missing_required_metadata_is_unconfirmed(
    client: OAuth2Api,
    field: RequiredTokenField,
) -> None:
    token = _token().model_copy(update={field: None})

    with (
        patch.object(client, "introspect_o_auth2_token", return_value=token),
        pytest.raises(DependencyUnavailableError),
    ):
        await HydraAccessTokenVerifier(client, SETTINGS, AUTHORITY).verify(
            CREDENTIAL,
            timeout_seconds=2.0,
        )


@pytest.mark.asyncio
async def test_non_uuid_subject_cannot_be_resolved_by_email(client: OAuth2Api) -> None:
    token = _token().model_copy(update={"sub": "alice@example.test"})

    with (
        patch.object(client, "introspect_o_auth2_token", return_value=token),
        pytest.raises(DependencyUnavailableError),
    ):
        await HydraAccessTokenVerifier(client, SETTINGS, AUTHORITY).verify(
            CREDENTIAL,
            timeout_seconds=2.0,
        )


@pytest.mark.asyncio
async def test_null_provider_body_is_unconfirmed(client: OAuth2Api) -> None:
    with (
        patch.object(client, "introspect_o_auth2_token", return_value=None),
        pytest.raises(DependencyUnavailableError),
    ):
        await HydraAccessTokenVerifier(client, SETTINGS, AUTHORITY).verify(
            CREDENTIAL,
            timeout_seconds=2.0,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        ApiException(status=401),
        ApiException(status=403),
        ApiException(status=500),
        HTTPError("Synthetic network failure."),
        TimeoutError(),
        JSONDecodeError("Malformed JSON.", "", 0),
    ],
)
async def test_provider_errors_are_unconfirmed(
    client: OAuth2Api,
    failure: Exception,
) -> None:
    with (
        patch.object(client, "introspect_o_auth2_token", side_effect=failure),
        pytest.raises(DependencyUnavailableError),
    ):
        await HydraAccessTokenVerifier(client, SETTINGS, AUTHORITY).verify(
            CREDENTIAL,
            timeout_seconds=2.0,
        )


@pytest.mark.asyncio
async def test_sdk_schema_error_is_unconfirmed(client: OAuth2Api) -> None:
    with pytest.raises(ValidationError) as invalid:
        IntrospectedOAuth2Token.model_validate({"active": "true"})

    with (
        patch.object(client, "introspect_o_auth2_token", side_effect=invalid.value),
        pytest.raises(DependencyUnavailableError),
    ):
        await HydraAccessTokenVerifier(client, SETTINGS, AUTHORITY).verify(
            CREDENTIAL,
            timeout_seconds=2.0,
        )


@pytest.mark.asyncio
async def test_provider_error_text_is_hidden_from_traceback(client: OAuth2Api) -> None:
    failure = ApiException(status=500, reason=CREDENTIAL.value)

    with (
        patch.object(client, "introspect_o_auth2_token", side_effect=failure),
        pytest.raises(DependencyUnavailableError) as caught,
    ):
        await HydraAccessTokenVerifier(client, SETTINGS, AUTHORITY).verify(
            CREDENTIAL,
            timeout_seconds=2.0,
        )

    assert CREDENTIAL.value not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


@pytest.mark.asyncio
async def test_provider_deadline_stops_waiting_for_the_sdk(client: OAuth2Api) -> None:
    release = Event()

    def blocked_call(**_kwargs: object) -> IntrospectedOAuth2Token:
        release.wait(timeout=1.0)
        return _token()

    try:
        with patch.object(client, "introspect_o_auth2_token", side_effect=blocked_call):
            async with asyncio.timeout(2.0):
                with pytest.raises(DependencyUnavailableError):
                    await HydraAccessTokenVerifier(client, SETTINGS, AUTHORITY).verify(
                        CREDENTIAL,
                        timeout_seconds=0.02,
                    )
    finally:
        release.set()


@pytest.mark.asyncio
async def test_next_request_rechecks_hydra(client: OAuth2Api) -> None:
    verifier = HydraAccessTokenVerifier(client, SETTINGS, AUTHORITY)

    with patch.object(
        client,
        "introspect_o_auth2_token",
        side_effect=[_token(), IntrospectedOAuth2Token(active=False)],
    ) as introspect:
        first = await verifier.verify(CREDENTIAL, timeout_seconds=2.0)
        second = await verifier.verify(CREDENTIAL, timeout_seconds=2.0)

    assert first is not None
    assert second is None
    assert introspect.call_count == 2
