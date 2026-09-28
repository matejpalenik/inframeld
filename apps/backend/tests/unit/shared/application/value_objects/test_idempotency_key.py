import pytest

from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey


def test_accepts_a_key_at_the_length_limit() -> None:
    value = "x" * 128

    assert IdempotencyKey(value).value == value


@pytest.mark.parametrize("value", ["", "   ", "x" * 129])
def test_rejects_blank_or_overlong_keys(value: str) -> None:
    with pytest.raises(ValueError, match="Idempotency key"):
        IdempotencyKey(value)
