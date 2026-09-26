"""Verify typed runtime configuration and sanitized validation errors."""

import pytest
from pydantic import SecretStr, ValidationError

from inframeld_backend.access.domain.values import IdentityAuthority
from inframeld_backend.shared.infrastructure.settings import DatabaseSettings, get_settings


def test_database_settings_rejects_non_positive_startup_timeout() -> None:
    """Prove invalid startup timeout configuration is rejected."""

    with pytest.raises(ValidationError):
        DatabaseSettings(
            name="test", user="test", password=SecretStr("test"), startup_timeout_seconds=0
        )


def test_invalid_configuration_error_does_not_expose_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove configuration errors identify invalid fields without exposing passwords."""

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


def test_kratos_settings_parse_url_and_authority_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parse configured Kratos values into URL and authority types."""

    monkeypatch.setenv("INFRAMELD_KRATOS__PUBLIC_URL", "http://127.0.0.1:14433")
    monkeypatch.setenv("INFRAMELD_KRATOS__AUTHORITY", "kratos:test")
    get_settings.cache_clear()

    try:
        kratos = get_settings().kratos

        assert kratos is not None
        assert str(kratos.public_url) == "http://127.0.0.1:14433/"
        assert kratos.authority == IdentityAuthority("kratos:test")
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    ("public_url", "authority", "invalid_field"),
    [
        ("not-a-url", "kratos:test", "kratos.public_url"),
        ("http://127.0.0.1:14433", "   ", "kratos.authority"),
    ],
)
def test_invalid_kratos_settings_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    public_url: str,
    authority: str,
    invalid_field: str,
) -> None:
    """Reject malformed Kratos configuration at the settings boundary."""

    monkeypatch.setenv("INFRAMELD_KRATOS__PUBLIC_URL", public_url)
    monkeypatch.setenv("INFRAMELD_KRATOS__AUTHORITY", authority)
    get_settings.cache_clear()

    try:
        with pytest.raises(RuntimeError) as error:
            get_settings()

        assert invalid_field in str(error.value)
    finally:
        get_settings.cache_clear()
