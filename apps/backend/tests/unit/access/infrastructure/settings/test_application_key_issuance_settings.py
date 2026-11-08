"""Keep fresh issuance defaults bounded without changing an original result."""

import pytest
from pydantic import ValidationError

from inframeld_backend.access.infrastructure.settings.application_key_issuance_settings import (
    ApplicationKeyIssuanceSettings,
)

DAY = 24 * 60 * 60


def test_default_key_lifetime_is_ninety_days_with_a_year_maximum() -> None:
    settings = ApplicationKeyIssuanceSettings()

    assert settings.default_lifetime_seconds == 90 * DAY
    assert settings.maximum_lifetime_seconds == 365 * DAY


@pytest.mark.parametrize("default,maximum", [(1, 1), (3600, DAY), (400 * DAY, 500 * DAY)])
def test_operator_may_configure_positive_whole_lifetimes(default: int, maximum: int) -> None:
    settings = ApplicationKeyIssuanceSettings(
        default_lifetime_seconds=default, maximum_lifetime_seconds=maximum
    )

    assert settings.default_lifetime_seconds == default
    assert settings.maximum_lifetime_seconds == maximum


def test_environment_whole_seconds_are_accepted() -> None:
    settings = ApplicationKeyIssuanceSettings.model_validate(
        {"default_lifetime_seconds": "3600", "maximum_lifetime_seconds": str(DAY)}
    )

    assert settings.default_lifetime_seconds == 3600
    assert settings.maximum_lifetime_seconds == DAY


@pytest.mark.parametrize("field", ["default_lifetime_seconds", "maximum_lifetime_seconds"])
@pytest.mark.parametrize("value", [0, -1, True, False, 1.0, 1.5, "1.5", None, 2**53])
def test_invalid_operator_lifetimes_are_rejected(field: str, value: object) -> None:
    values: dict[str, object] = {
        "default_lifetime_seconds": 1,
        "maximum_lifetime_seconds": DAY,
        field: value,
    }

    with pytest.raises(ValidationError):
        ApplicationKeyIssuanceSettings.model_validate(values)


def test_default_cannot_exceed_configured_maximum() -> None:
    with pytest.raises(ValidationError):
        ApplicationKeyIssuanceSettings(default_lifetime_seconds=DAY, maximum_lifetime_seconds=3600)


def test_unknown_configuration_is_rejected_without_rendering_its_value() -> None:
    with pytest.raises(ValidationError) as error:
        ApplicationKeyIssuanceSettings.model_validate({"unrecognized": "protected-config-value"})

    assert "protected-config-value" not in str(error.value)


def test_validated_lifetime_configuration_cannot_change_during_an_attempt() -> None:
    settings = ApplicationKeyIssuanceSettings()

    with pytest.raises(ValidationError):
        settings.default_lifetime_seconds = 1
