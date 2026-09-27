import pytest

from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)


def test_key_is_hidden_from_its_representation() -> None:
    key = RequestFingerprintKey(b"K" * 32)

    assert key.value == b"K" * 32
    assert "K" * 32 not in repr(key)


def test_short_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        RequestFingerprintKey(b"K" * 31)
