import pytest

from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)


@pytest.mark.parametrize("value", [True, False, 0, -1, 2**63, 1.0, "1", None])
def test_version_rejects_values_outside_positive_bigint(value: int) -> None:
    """A malformed provider value cannot become a trusted credential generation."""
    with pytest.raises(ValueError):
        HumanCredentialVersion(value)


@pytest.mark.parametrize("value", [1, 6, 2**63 - 1])
def test_version_preserves_valid_values(value: int) -> None:
    assert HumanCredentialVersion(value).value == value
