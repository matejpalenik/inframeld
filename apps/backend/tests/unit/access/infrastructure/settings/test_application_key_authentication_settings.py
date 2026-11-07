import pytest
from pydantic import ValidationError

from inframeld_backend.access.infrastructure.settings.application_key_authentication_settings import (
    ApplicationKeyAuthenticationSettings,
)
from inframeld_backend.access.infrastructure.types.application_key_transport_profile import (
    ApplicationKeyTransportProfile,
)


@pytest.mark.parametrize(
    "audience",
    [
        "http://remote.test",
        "https://user:private@api.test",
        "https://api.test?private=value",
        "https://api.test/#fragment",
        " https://api.test",
        "https://api.test/../mcp/",
    ],
)
def test_public_audiences_reject_unsafe_configuration_without_echo(audience: str) -> None:
    with pytest.raises(ValidationError) as error:
        ApplicationKeyAuthenticationSettings(http_audience=audience)
    assert audience not in str(error.value)
    assert "private@" not in str(error.value)


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), True])
def test_authentication_budget_is_finite_positive_and_not_boolean(timeout: float) -> None:
    with pytest.raises(ValidationError):
        ApplicationKeyAuthenticationSettings(total_timeout_seconds=timeout)


def test_profiles_are_independent_without_audience_equivalence_or_inequality_rule() -> None:
    first = ApplicationKeyAuthenticationSettings(
        http_audience="https://api.test", mcp_audience="https://api.test/mcp/"
    )
    same = ApplicationKeyAuthenticationSettings(
        http_audience="https://api.test/mcp/", mcp_audience="https://api.test/mcp/"
    )
    assert first.http_audience != first.mcp_audience
    assert same.http_audience == same.mcp_audience
    assert ApplicationKeyAuthenticationSettings().http_audience is None


def test_managed_local_profile_requires_literal_loopback_without_network_lookup() -> None:
    with pytest.raises(ValidationError):
        ApplicationKeyAuthenticationSettings(
            http_audience="http://localhost:8000",
            transport_profile=ApplicationKeyTransportProfile.MANAGED_LOCAL,
        )
    settings = ApplicationKeyAuthenticationSettings(
        http_audience="http://127.0.0.1:8000",
        transport_profile=ApplicationKeyTransportProfile.MANAGED_LOCAL,
    )
    assert settings.http_audience == "http://127.0.0.1:8000"
