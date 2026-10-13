"""Check deployment-configured human authentication limits."""

from typing import Literal

import pytest
from pydantic import ValidationError

from inframeld_backend.access.infrastructure.settings.human_authentication_settings import (
    HumanAuthenticationSettings,
)


def test_default_limits_match_the_accepted_authentication_budget() -> None:
    settings = HumanAuthenticationSettings()

    assert settings.provider_timeout_seconds == 5.0
    assert settings.total_timeout_seconds == 10.0


@pytest.mark.parametrize("provider_seconds", [0.5, 20.0])
def test_provider_limit_can_be_shorter_or_longer_than_total_limit(
    provider_seconds: float,
) -> None:
    """A longer provider limit is valid; the workflow still caps it by time remaining."""
    settings = HumanAuthenticationSettings(
        provider_timeout_seconds=provider_seconds,
        total_timeout_seconds=10.0,
    )

    assert settings.provider_timeout_seconds == provider_seconds


@pytest.mark.parametrize("field", ["provider_timeout_seconds", "total_timeout_seconds"])
@pytest.mark.parametrize(
    "seconds",
    [True, False, 0.0, -1.0, float("nan"), float("inf"), float("-inf"), "not-a-number"],
)
def test_invalid_authentication_limits_are_rejected(
    field: Literal["provider_timeout_seconds", "total_timeout_seconds"],
    seconds: object,
) -> None:
    """Reject values that could disable deadlines or accidentally treat True as one second."""
    with pytest.raises(ValidationError) as caught:
        HumanAuthenticationSettings.model_validate({field: seconds})

    assert caught.value.errors()[0]["loc"] == (field,)


def test_unknown_authentication_setting_is_rejected() -> None:
    """Catch a misspelled setting instead of silently using a default."""
    with pytest.raises(ValidationError):
        HumanAuthenticationSettings.model_validate({"provider_timout_seconds": 1.0})
