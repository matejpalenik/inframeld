import pytest
from pydantic import SecretStr, ValidationError

from inframeld_backend.shared.infrastructure.settings import DatabaseSettings, get_settings


def test_database_settings_rejects_non_positive_startup_timeout() -> None:
    with pytest.raises(ValidationError):
        DatabaseSettings(
            name="test", user="test", password=SecretStr("test"), startup_timeout_seconds=0
        )


def test_invalid_configuration_error_does_not_expose_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "INFRAMELD_DATABASE__HOST": "localhost",
        "INFRAMELD_DATABASE__PORT": "not-a-port",
        "INFRAMELD_DATABASE__NAME": "test",
        "INFRAMELD_DATABASE__USER": "test",
        "INFRAMELD_DATABASE__PASSWORD": "super-secret-password123+",
    }

    for name, value in values.items():
        monkeypatch.setenv(name, value)

    get_settings.cache_clear()

    try:
        with pytest.raises(RuntimeError) as error:
            get_settings()

        message = str(error.value)

        assert "database.port" in message
        assert "super-secret-password123+" not in message
    finally:
        get_settings.cache_clear()
