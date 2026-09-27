"""Load the persistent idempotency fingerprint key from a protected file."""

from pathlib import Path
from typing import final

from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)


@final
class FileRequestFingerprintKeyReader:
    """Read an existing raw key without creating or rotating it."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> RequestFingerprintKey:
        """Return the deployment key - fail if the file is missing or malformed."""

        try:
            with self._path.open("rb") as key_file:
                material = key_file.read(33)
        except OSError as exc:
            raise RuntimeError("Cannot read the idempotency fingerprint key file.") from exc

        if len(material) != 32:
            raise RuntimeError("Idempotency fingerprint key file must contain exactly 32 bytes.")

        return RequestFingerprintKey(material)
