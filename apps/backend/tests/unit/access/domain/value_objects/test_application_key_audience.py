import pytest

from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)


@pytest.mark.parametrize("value", ["", " ", "\n"])
def test_audience_must_have_an_exact_nonblank_value(value: str) -> None:
    with pytest.raises(ValueError):
        ApplicationKeyAudience(value)


def test_audience_equality_has_no_alias_or_normalization() -> None:
    assert ApplicationKeyAudience("https://api.test") != ApplicationKeyAudience("https://api.test/")
