"""Verify typed runtime configuration and sanitized validation errors."""

import os
from pathlib import Path

import pytest
from pydantic import HttpUrl, SecretStr, ValidationError

from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.bootstrap.application_settings import ApplicationSettings, get_settings
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.settings.request_fingerprint_settings import (
    RequestFingerprintSettings,
)


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


def test_csrf_origins_parse_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parse the browser-origin allowlist from its nested environment value."""
    monkeypatch.setenv(
        "INFRAMELD_CSRF__TRUSTED_ORIGINS",
        '["http://127.0.0.1:8000"]',
    )
    get_settings.cache_clear()

    try:
        assert get_settings().csrf.trusted_origins == (HttpUrl("http://127.0.0.1:8000"),)
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


def test_fingerprint_key_path_is_read_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Give the process a file location without putting key bytes in its environment."""
    path = Path("/run/secrets/idempotency_fingerprint_hmac")
    monkeypatch.setenv("INFRAMELD_REQUEST_FINGERPRINT__KEY_FILE", str(path))
    get_settings.cache_clear()

    try:
        assert get_settings().request_fingerprint.key_file == path
    finally:
        get_settings.cache_clear()


def test_fingerprint_key_path_must_be_absolute() -> None:
    """Avoid resolving a deployment secret relative to an unpredictable working directory."""
    with pytest.raises(ValidationError, match="absolute"):
        RequestFingerprintSettings(key_file=Path("relative/fingerprint.key"))


@pytest.fixture
def bearer_configuration_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep configuration cases independent of the developer's inherited environment."""
    for name in tuple(os.environ):
        if name.startswith("INFRAMELD_"):
            monkeypatch.delenv(name, raising=False)


def _load_bearer_settings() -> ApplicationSettings:
    # Explicit values and _env_file=None isolate tests from real configuration.
    return ApplicationSettings(
        database=DatabaseSettings(
            name="synthetic",
            user="synthetic",
            password=SecretStr("synthetic-password"),
        ),
        request_fingerprint=RequestFingerprintSettings(
            key_file=Path("/run/secrets/synthetic-fingerprint.key")
        ),
        # BaseSettings supports this; its generated model signature omits it.
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )


def _configure_kratos(
    monkeypatch: pytest.MonkeyPatch,
    *,
    with_admin_url: bool,
) -> None:
    monkeypatch.setenv("INFRAMELD_KRATOS__PUBLIC_URL", "http://kratos:4433")
    monkeypatch.setenv("INFRAMELD_KRATOS__AUTHORITY", "kratos:test")
    if with_admin_url:
        monkeypatch.setenv("INFRAMELD_KRATOS__ADMIN_URL", "http://kratos:4434")


def _configure_hydra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFRAMELD_HYDRA__ADMIN_URL", "http://hydra:4445")
    monkeypatch.setenv("INFRAMELD_HYDRA__ISSUER", "https://login.example.test/")
    monkeypatch.setenv("INFRAMELD_HYDRA__API_AUDIENCE", "https://api.example.test")


def test_cookie_only_environment_remains_valid(
    bearer_configuration_environment: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Allow browser login without requiring Hydra or a Kratos admin endpoint."""
    _configure_kratos(monkeypatch, with_admin_url=False)

    settings = _load_bearer_settings()

    assert settings.hydra is None
    assert settings.kratos is not None
    assert settings.kratos.admin_url is None


def test_complete_human_bearer_environment_is_parsed(
    bearer_configuration_environment: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Load both private endpoints and the exact Hydra issuer and API audience."""
    _configure_kratos(monkeypatch, with_admin_url=True)
    _configure_hydra(monkeypatch)

    settings = _load_bearer_settings()

    assert settings.kratos is not None
    assert settings.kratos.admin_url == HttpUrl("http://kratos:4434")
    assert settings.kratos.authority == IdentityAuthority("kratos:test")
    assert settings.hydra is not None
    assert settings.hydra.admin_url == HttpUrl("http://hydra:4445")
    assert settings.hydra.issuer.value == "https://login.example.test/"
    assert settings.hydra.api_audience.value == "https://api.example.test"


def test_hydra_requires_kratos_configuration(
    bearer_configuration_environment: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject token verification without a configured source of current identity state."""
    _configure_hydra(monkeypatch)

    with pytest.raises(ValidationError, match="requires Kratos configuration"):
        _load_bearer_settings()


def test_hydra_requires_an_explicit_kratos_admin_url(
    bearer_configuration_environment: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject bearer configuration that cannot perform the required Kratos identity lookup."""
    _configure_kratos(monkeypatch, with_admin_url=False)
    _configure_hydra(monkeypatch)

    with pytest.raises(ValidationError, match="requires an explicit Kratos admin URL"):
        _load_bearer_settings()


def test_kratos_admin_url_alone_does_not_require_hydra(
    bearer_configuration_environment: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep a configured Kratos admin client independent of whether Hydra is enabled."""
    _configure_kratos(monkeypatch, with_admin_url=True)

    settings = _load_bearer_settings()

    assert settings.hydra is None
    assert settings.kratos is not None
    assert settings.kratos.admin_url == HttpUrl("http://kratos:4434")


def test_human_authentication_limits_have_safe_environment_defaults(
    bearer_configuration_environment: None,
) -> None:
    settings = _load_bearer_settings().human_authentication

    assert settings.provider_timeout_seconds == 5.0
    assert settings.total_timeout_seconds == 10.0


@pytest.mark.parametrize("with_total_override", [False, True])
def test_human_authentication_limits_parse_from_environment(
    bearer_configuration_environment: None,
    monkeypatch: pytest.MonkeyPatch,
    with_total_override: bool,
) -> None:
    """Parse numeric strings while retaining the default for an omitted nested value."""
    monkeypatch.setenv(
        "INFRAMELD_HUMAN_AUTHENTICATION__PROVIDER_TIMEOUT_SECONDS",
        "2.5",
    )
    if with_total_override:
        monkeypatch.setenv(
            "INFRAMELD_HUMAN_AUTHENTICATION__TOTAL_TIMEOUT_SECONDS",
            "7.0",
        )

    settings = _load_bearer_settings().human_authentication

    assert settings.provider_timeout_seconds == 2.5
    assert settings.total_timeout_seconds == (7.0 if with_total_override else 10.0)


@pytest.mark.parametrize(
    ("name", "field"),
    [
        (
            "INFRAMELD_HUMAN_AUTHENTICATION__PROVIDER_TIMEOUT_SECONDS",
            "provider_timeout_seconds",
        ),
        (
            "INFRAMELD_HUMAN_AUTHENTICATION__TOTAL_TIMEOUT_SECONDS",
            "total_timeout_seconds",
        ),
    ],
)
@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "true"])
def test_invalid_human_authentication_environment_is_rejected(
    bearer_configuration_environment: None,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    field: str,
    value: str,
) -> None:
    """Reject unusable deployment limits and identify the offending field."""
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError) as caught:
        _load_bearer_settings()

    assert caught.value.errors()[0]["loc"] == ("human_authentication", field)


def test_consent_settings_parse_explicit_public_url_and_remember_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INFRAMELD_KRATOS__ADMIN_URL", "http://kratos:4434")
    monkeypatch.setenv("INFRAMELD_HYDRA__ADMIN_URL", "http://hydra:4445")
    monkeypatch.setenv("INFRAMELD_HYDRA__PUBLIC_URL", "https://auth.test/hydra")
    monkeypatch.setenv("INFRAMELD_HYDRA__ISSUER", "https://auth.test/hydra/")
    monkeypatch.setenv("INFRAMELD_HYDRA__API_AUDIENCE", "https://api.test")
    monkeypatch.setenv("INFRAMELD_HYDRA__REMEMBER_CONSENT_SECONDS", "7200")
    get_settings.cache_clear()
    try:
        settings = get_settings().hydra
        assert settings is not None
        assert str(settings.public_url) == "https://auth.test/hydra"
        assert settings.remember_consent_seconds == 7200
    finally:
        get_settings.cache_clear()
