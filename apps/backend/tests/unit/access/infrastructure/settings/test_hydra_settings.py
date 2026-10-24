from typing import Literal

import pytest
from pydantic import ValidationError

from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience
from inframeld_backend.access.domain.value_objects.oauth_issuer import OAuthIssuer
from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings


def _settings_input() -> dict[str, object]:
    return {
        "admin_url": "http://hydra:4445",
        "issuer": "https://login.example.test",
        "api_audience": "https://api.example.test/base",
    }


def test_configuration_preserves_exact_issuer_and_audience_text() -> None:
    settings = HydraSettings.model_validate(_settings_input())

    assert settings.issuer == OAuthIssuer("https://login.example.test")
    assert settings.api_audience == HumanAPIAudience("https://api.example.test/base")
    assert settings.client_id == "inframeld-cli"
    assert settings.required_scope == "inframeld:api"


@pytest.mark.parametrize("field", ["admin_url", "issuer", "api_audience"])
@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "ftp://example.test",
        "https://user:password@example.test",
        "https://example.test?target=another",
        "https://example.test#fragment",
    ],
)
def test_rejects_invalid_or_credential_bearing_urls(
    field: Literal["admin_url", "issuer", "api_audience"],
    url: str,
) -> None:
    inputs = _settings_input()
    inputs[field] = url

    with pytest.raises(ValidationError):
        HydraSettings.model_validate(inputs)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("client_id", "another-client"),
        ("required_scope", "openid"),
    ],
)
def test_requires_the_accepted_first_party_client_and_api_scope(
    field: Literal["client_id", "required_scope"],
    value: str,
) -> None:
    inputs = _settings_input()
    inputs[field] = value

    with pytest.raises(ValidationError):
        HydraSettings.model_validate(inputs)


def test_consent_configuration_defaults_to_one_hour_and_requires_an_explicit_public_url() -> None:
    settings = HydraSettings.model_validate(_settings_input())
    assert settings.remember_consent_seconds == 3600
    assert settings.public_url is None


@pytest.mark.parametrize("seconds", [True, 0, -1, 1.5, "forever"])
def test_remembered_consent_cannot_be_unbounded_or_fractional(seconds: object) -> None:
    inputs = _settings_input() | {"remember_consent_seconds": seconds}
    with pytest.raises(ValidationError):
        HydraSettings.model_validate(inputs)


@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@auth.test",
        "https://auth.test?x=y",
        "https://auth.test#x",
        "ftp://auth.test",
    ],
)
def test_public_consent_endpoint_rejects_unsafe_configuration(url: str) -> None:
    with pytest.raises(ValidationError):
        HydraSettings.model_validate(_settings_input() | {"public_url": url})
