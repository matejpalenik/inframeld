import pytest

from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


@pytest.mark.parametrize(
    "value", ["", "A", " name", "name ", "9name", "name-", "na_me", "é", "a" * 64]
)
def test_rejects_invalid_exact_selector_without_normalization(value: str) -> None:
    with pytest.raises(ValueError):
        ResourceName(value)


def test_limits_and_production_are_valid() -> None:
    assert ResourceName("production").value == "production"
    assert ResourceName("a" * 63).value == "a" * 63


def test_preview_never_truncates_or_repairs_invalid_start() -> None:
    assert ResourceName.suggest("Légal Research") == ResourceName("legal-research")
    assert ResourceName.suggest("123") is None
    assert ResourceName.suggest("a" * 64) is None
