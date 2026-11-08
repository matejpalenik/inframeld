"""Validate operator lifetime policy without configuring providers or issuing an invitation."""

import pytest
from pydantic import ValidationError

from inframeld_backend.access.infrastructure.settings.invitation_settings import InvitationSettings

DAY = 24 * 60 * 60


def test_default_lifetime_is_seven_days_with_a_thirty_day_maximum() -> None:
    settings = InvitationSettings()

    assert settings.default_lifetime_seconds == 7 * DAY
    assert settings.maximum_lifetime_seconds == 30 * DAY


@pytest.mark.parametrize("default,maximum", [(1, 1), (3600, DAY), (30 * DAY, 30 * DAY)])
def test_positive_bounded_operator_lifetimes_are_preserved(default: int, maximum: int) -> None:
    settings = InvitationSettings(
        default_lifetime_seconds=default, maximum_lifetime_seconds=maximum
    )

    assert settings.default_lifetime_seconds == default
    assert settings.maximum_lifetime_seconds == maximum


def test_operator_numeric_strings_are_parsed_as_whole_seconds() -> None:
    settings = InvitationSettings.model_validate(
        {"default_lifetime_seconds": "3600", "maximum_lifetime_seconds": str(DAY)}
    )

    assert settings.default_lifetime_seconds == 3600
    assert settings.maximum_lifetime_seconds == DAY


@pytest.mark.parametrize("field", ["default_lifetime_seconds", "maximum_lifetime_seconds"])
@pytest.mark.parametrize("value", [0, -1, "0", "-1"])
def test_each_lifetime_requires_positive_seconds(field: str, value: object) -> None:
    values: dict[str, object] = {
        "default_lifetime_seconds": 1,
        "maximum_lifetime_seconds": DAY,
        field: value,
    }

    with pytest.raises(ValidationError) as error:
        InvitationSettings.model_validate(values)

    assert any(item["loc"] == (field,) for item in error.value.errors())


@pytest.mark.parametrize("field", ["default_lifetime_seconds", "maximum_lifetime_seconds"])
@pytest.mark.parametrize("value", [True, False, 1.0, 1.5, "1.0", "1.5", "true", None])
def test_booleans_fractions_and_non_integer_inputs_do_not_become_lifetimes(
    field: str,
    value: object,
) -> None:
    values: dict[str, object] = {
        "default_lifetime_seconds": 1,
        "maximum_lifetime_seconds": DAY,
        field: value,
    }

    with pytest.raises(ValidationError) as error:
        InvitationSettings.model_validate(values)

    assert any(item["loc"] == (field,) for item in error.value.errors())


@pytest.mark.parametrize("field", ["default_lifetime_seconds", "maximum_lifetime_seconds"])
def test_operator_configuration_cannot_raise_the_thirty_day_cap(field: str) -> None:
    with pytest.raises(ValidationError):
        InvitationSettings.model_validate({field: 30 * DAY + 1})


def test_default_cannot_exceed_a_shorter_configured_maximum() -> None:
    with pytest.raises(ValidationError):
        InvitationSettings(default_lifetime_seconds=DAY, maximum_lifetime_seconds=3600)


def test_unknown_configuration_is_rejected_without_echoing_its_value() -> None:
    with pytest.raises(ValidationError) as error:
        InvitationSettings.model_validate({"unrecognized_setting": "private-operator-value"})

    assert "private-operator-value" not in str(error.value)


def test_validated_lifetime_configuration_is_frozen() -> None:
    settings = InvitationSettings()

    with pytest.raises(ValidationError):
        settings.default_lifetime_seconds = 1
