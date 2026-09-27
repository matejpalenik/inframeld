from pathlib import Path

import pytest

from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.infrastructure.readers.file_request_fingerprint_key_reader import (
    FileRequestFingerprintKeyReader,
)


def test_repeated_reader_instances_use_the_same_stored_key(tmp_path: Path) -> None:
    """A restart must preserve fingerprints for requests still in retention."""
    path = tmp_path / "fingerprint.key"
    path.write_bytes(b"K" * 32)

    first = RequestFingerprintService(FileRequestFingerprintKeyReader(path).read())
    second = RequestFingerprintService(FileRequestFingerprintKeyReader(path).read())

    request = b'{"secret":"example"}'
    assert first.fingerprint(
        purpose="provider-credential-update:v1",
        canonical_request=request,
    ) == second.fingerprint(
        purpose="provider-credential-update:v1",
        canonical_request=request,
    )


def test_missing_key_fails_without_creating_a_replacement(tmp_path: Path) -> None:
    """A lost key must not silently change the identity of old requests."""
    path = tmp_path / "missing.key"

    with pytest.raises(RuntimeError, match="Cannot read the idempotency fingerprint key file"):
        FileRequestFingerprintKeyReader(path).read()

    assert not path.exists()


@pytest.mark.parametrize("contents", [b"", b"K" * 31, b"K" * 33, b"K" * 32 + b"\n"])
def test_malformed_key_fails_without_exposing_its_contents(tmp_path: Path, contents: bytes) -> None:
    """Reject short, oversized, and newline-terminated files safely."""
    path = tmp_path / "fingerprint.key"
    path.write_bytes(contents)

    with pytest.raises(RuntimeError, match="must contain exactly 32 bytes") as failure:
        FileRequestFingerprintKeyReader(path).read()

    if contents:
        assert contents not in str(failure.value).encode()
