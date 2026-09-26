"""Load aggregate application settings from validated environment configuration."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from inframeld_backend.access.infrastructure.kratos.kratos_settings import KratosSettings
from inframeld_backend.shared.infrastructure.observability.logging_settings import (
    LogFormat,
    LogLevel,
)
from inframeld_backend.shared.infrastructure.postgres.database_settings import DatabaseSettings

BACKEND_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENV_FILE = BACKEND_ROOT / ".env"
DEFAULT_TEST_ENV_FILE = BACKEND_ROOT / ".env.test"


class ApplicationSettings(BaseSettings):
    """Validate aggregate process configuration and compose provider-specific settings.

    Environment names and defaults are shared by HTTP startup, migration tooling,
    and tests. This object contains configuration, not opened external resources."""

    environment: Literal["local", "test", "production"] = "local"
    log_level: LogLevel = "INFO"
    log_format: LogFormat = "console"

    database: DatabaseSettings
    kratos: KratosSettings | None = None

    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="INFRAMELD_",
        env_nested_delimiter="__",
        extra="forbid",
    )


def _format_validation_error(error: ValidationError) -> str:
    """Describe invalid configuration fields without rendering the supplied input values."""
    details = "\n".join(
        f"- {'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors()
    )
    return f"Invalid runtime configuration:\n{details}"


def _settings_env_file() -> Path | None:
    """Select the explicit test environment file or the ordinary backend environment file."""
    if os.getenv("INFRAMELD_ENVIRONMENT") != "test":
        return DEFAULT_ENV_FILE

    configured_path = os.getenv("INFRAMELD_TEST_ENV_FILE")
    env_file = Path(configured_path).expanduser() if configured_path else DEFAULT_TEST_ENV_FILE

    if not env_file.is_absolute():
        env_file = BACKEND_ROOT / env_file

    env_file = env_file.resolve()

    if not env_file.is_file():
        raise RuntimeError(
            f"Missing test configuration file: {env_file}. "
            "Create apps/backend/.env.test before running tests."
        )

    return env_file


@lru_cache(maxsize=1)
def get_settings() -> ApplicationSettings:
    """Load and cache validated application settings."""
    try:
        # BaseSettings reads required fields from the environment; its generated
        # signature still declares them as required constructor arguments.
        return ApplicationSettings(_env_file=_settings_env_file())  # pyright: ignore[reportCallIssue]
    except ValidationError as error:
        raise RuntimeError(_format_validation_error(error)) from None
