import stat
from pathlib import Path

from inframeld_backend.access.infrastructure.settings.recovery_notification_settings import (
    RecoveryNotificationSettings,
)
from inframeld_backend.access.infrastructure.types.recovery_hook_credentials import (
    RecoveryHookCredentials,
)


class FileRecoveryHookCredentialsReader:
    def __init__(self, settings: RecoveryNotificationSettings) -> None:
        self._settings = settings

    def read(self) -> RecoveryHookCredentials:
        settings = self._settings
        return RecoveryHookCredentials(
            current=self._read_key(settings.current_key_file),
            retiring=None
            if settings.retiring_key_file is None
            else self._read_key(settings.retiring_key_file),
            retiring_accept_until=settings.retiring_key_accept_until,
        )

    def _read_key(self, path: Path) -> bytes:
        try:
            mode = path.stat().st_mode
            if not stat.S_ISREG(mode) or mode & 0o077:
                raise ValueError("Hook keys require protected regular files.")
            with path.open("rb") as key_file:
                key = key_file.read(258)
            if key.endswith(b"\n"):
                key = key[:-1]
            if not 32 <= len(key) <= 256 or any(c < 33 or c > 126 for c in key):
                raise ValueError("Hook keys require 32 to 256 printable ASCII bytes.")
            return key
        except OSError:
            raise ValueError("The recovery hook key is unavailable.") from None
