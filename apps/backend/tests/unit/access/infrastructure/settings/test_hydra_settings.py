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
