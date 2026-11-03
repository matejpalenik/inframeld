import pytest

from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)


def test_complete_content_uses_sha256_not_storage_metadata() -> None:
    digest = ArtifactContentDigest.from_content(b"abc")
    assert digest.value.hex() == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert digest.value.hex() not in repr(digest)


@pytest.mark.parametrize("value", [b"", b"x" * 31, b"x" * 33])
def test_rejects_non_sha256_content_identity(value: bytes) -> None:
    with pytest.raises(ValueError):
        ArtifactContentDigest(value)


def test_storage_etag_cannot_be_used_as_the_binary_content_digest() -> None:
    with pytest.raises(TypeError):
        ArtifactContentDigest('"etag"')  # type: ignore[arg-type]
