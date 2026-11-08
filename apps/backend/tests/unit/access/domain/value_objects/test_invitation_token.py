"""Keep the public token canonical and its retained verifier secret-free."""

import base64
import hashlib
import re

import pytest

from inframeld_backend.access.domain.value_objects.invitation_token import InvitationToken
from inframeld_backend.access.domain.value_objects.invitation_token_digest import (
    InvitationTokenDigest,
)

TOKEN = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii").rstrip("=")


def test_generated_token_contains_32_bytes_as_43_unpadded_urlsafe_characters() -> None:
    token = InvitationToken.generate()

    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token.value)
    assert len(base64.urlsafe_b64decode(token.value + "=")) == 32
    assert token.value not in repr(token)


def test_only_digest_is_needed_to_recognize_the_delivered_token() -> None:
    delivered = InvitationToken(TOKEN)
    retained = delivered.digest()
    received = InvitationToken(TOKEN)

    assert retained.value == hashlib.sha256(TOKEN.encode("ascii")).digest()
    assert retained.matches(received.digest())
    assert TOKEN not in repr(retained)
    assert repr(retained.value) not in repr(retained)


@pytest.mark.parametrize("changed_byte", [0, 15, 31])
def test_different_token_digest_never_matches(changed_byte: int) -> None:
    original = bytearray(range(32))
    original[changed_byte] ^= 1
    changed = base64.urlsafe_b64encode(original).decode("ascii").rstrip("=")

    assert not InvitationToken(TOKEN).digest().matches(InvitationToken(changed).digest())


@pytest.mark.parametrize(
    "value",
    [
        "",
        "A" * 42,
        "A" * 44,
        "A" * 42 + "=",
        "A" * 42 + "+",
        "A" * 42 + "/",
        "A" * 42 + " ",
        "A" * 42 + "\n",
        "é" + "A" * 42,
        "A" * 42 + "B",
    ],
)
def test_malformed_or_noncanonical_token_is_rejected_without_echoing_secret(value: str) -> None:
    with pytest.raises(ValueError) as error:
        InvitationToken(value)

    if value:
        assert value not in str(error.value)


@pytest.mark.parametrize("value", [b"", b"x" * 31, b"x" * 33])
def test_digest_requires_exact_sha256_size(value: bytes) -> None:
    with pytest.raises(ValueError):
        InvitationTokenDigest(value)
