from typing import cast

import pytest

from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


def test_preserves_the_exact_digest_bytes() -> None:
    digest = bytes(range(32))
    assert RequestFingerprint(digest).value == digest


@pytest.mark.parametrize("value", [None, "digest", bytearray(32)])
def test_rejects_values_that_are_not_immutable_bytes(value: object) -> None:
    """Mutable buffers and text must not become a request's saved identity."""
    with pytest.raises(TypeError, match="Fingerprint"):
        RequestFingerprint(cast(bytes, value))


@pytest.mark.parametrize("value", [b"", b"F" * 31, b"F" * 33])
def test_rejects_an_incomplete_or_unexpected_digest(value: bytes) -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        RequestFingerprint(value)
