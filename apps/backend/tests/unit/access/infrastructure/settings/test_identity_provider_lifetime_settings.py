import pytest
from pydantic import ValidationError

from inframeld_backend.access.infrastructure.settings.identity_provider_lifetime_settings import (
    IdentityProviderLifetimeSettings,
)


def test_native_lifetime_defaults_match_the_selected_profile() -> None:
    settings = IdentityProviderLifetimeSettings()
    assert (
        settings.access_token,
        settings.refresh_token,
        settings.auth_code,
        settings.browser_session,
    ) == ("5m", "168h", "1m", "8h")


@pytest.mark.parametrize(
    "field", ["TTL_ACCESS_TOKEN", "TTL_REFRESH_TOKEN", "TTL_AUTH_CODE", "SESSION_LIFESPAN"]
)
@pytest.mark.parametrize(
    "value",
    [
        "0s",
        "-1",
        "-1s",
        "forever",
        "nan",
        "1.5h",
        "999999999999999999999h",
        " 5m",
        "5m-secret",
        "５m",
        "١h",
        "5m١s",
        "1h３０m",
    ],
)
def test_invalid_native_lifetime_is_rejected_without_echoing_input(field: str, value: str) -> None:
    with pytest.raises(ValidationError) as failure:
        IdentityProviderLifetimeSettings.model_validate({field: value})
    assert "5m-secret" not in str(failure.value)


@pytest.mark.parametrize("value", ["1ns", "300s", "1h30m", "168h"])
def test_finite_positive_native_durations_are_preserved(value: str) -> None:
    assert (
        IdentityProviderLifetimeSettings.model_validate({"TTL_ACCESS_TOKEN": value}).access_token
        == value
    )
