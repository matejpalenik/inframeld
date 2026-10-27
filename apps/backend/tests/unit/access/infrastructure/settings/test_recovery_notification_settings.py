from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.infrastructure.readers.file_recovery_hook_credentials_reader import (
    FileRecoveryHookCredentialsReader,
)
from inframeld_backend.access.infrastructure.settings.recovery_notification_settings import (
    RecoveryNotificationSettings,
)
from inframeld_backend.bootstrap.recovery_application_settings import RecoveryApplicationSettings


def _key(tmp_path: Path) -> Path:
    path = tmp_path / "hook.key"
    path.write_bytes(b"test-only-key-with-at-least-32-bytes\n")
    path.chmod(0o600)
    return path


def test_private_settings_need_no_browser_hydra_or_fingerprint_configuration(
    tmp_path: Path,
) -> None:
    settings = RecoveryApplicationSettings.model_validate(
        {
            "database": {"name": "recovery", "user": "test", "password": "not-production"},
            "recovery": {"authority": "https://identity.test", "current_key_file": _key(tmp_path)},
        }
    )
    assert settings.recovery.request_timeout_seconds == 10
    assert settings.recovery.database_timeout_seconds == 5
    credentials = FileRecoveryHookCredentialsReader(settings.recovery).read()
    assert credentials.current == b"test-only-key-with-at-least-32-bytes"
    assert "test-only-key" not in repr(credentials)


@pytest.mark.parametrize(
    "change",
    [
        {"retiring_key_file": "/private/key"},
        {"retiring_key_accept_until": datetime.now(UTC)},
        {"retiring_key_file": "/private/key", "retiring_key_accept_until": datetime(2026, 1, 1)},
        {"request_timeout_seconds": float("inf")},
        {"database_timeout_seconds": 6},
        {"request_timeout_seconds": 4},
        {"database_timeout_seconds": 0},
    ],
)
def test_invalid_rotation_and_deadlines_are_rejected(
    tmp_path: Path, change: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        RecoveryNotificationSettings.model_validate(
            {"authority": "https://identity.test", "current_key_file": _key(tmp_path)} | change
        )


def test_protected_key_rotation_loads_both_keys(tmp_path: Path) -> None:
    path = _key(tmp_path)
    settings = RecoveryNotificationSettings(
        authority=IdentityAuthority("https://identity.test"),
        current_key_file=path,
        retiring_key_file=path,
        retiring_key_accept_until=datetime.now(UTC) + timedelta(hours=1),
    )
    loaded = FileRecoveryHookCredentialsReader(settings).read()
    assert loaded.current == loaded.retiring


@pytest.mark.parametrize("content", [b"short", b"x" * 257, b"x" * 31 + b" ", b"x" * 32 + b"\x00"])
def test_malformed_keys_fail_without_echoing_values(tmp_path: Path, content: bytes) -> None:
    path = _key(tmp_path)
    path.write_bytes(content)
    settings = RecoveryNotificationSettings(
        authority=IdentityAuthority("https://identity.test"), current_key_file=path
    )
    with pytest.raises(ValueError) as error:
        FileRecoveryHookCredentialsReader(settings).read()
    assert content.decode(errors="ignore") not in str(error.value)


def test_group_readable_key_is_refused(tmp_path: Path) -> None:
    path = _key(tmp_path)
    path.chmod(0o640)
    with pytest.raises(ValueError, match="protected"):
        FileRecoveryHookCredentialsReader(
            RecoveryNotificationSettings(
                authority=IdentityAuthority("https://identity.test"), current_key_file=path
            )
        ).read()
