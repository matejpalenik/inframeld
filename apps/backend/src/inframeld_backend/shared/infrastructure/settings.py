import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

Port = Annotated[int, Field(ge=1, le=65_535)]
PoolSize = Annotated[int, Field(ge=1, le=100)]
PoolOverflow = Annotated[int, Field(ge=0, le=100)]
ConnectTimeoutSeconds = Annotated[int, Field(ge=1, le=60)]
StartupTimeoutSeconds = Annotated[float, Field(gt=0, le=60)]
PoolTimeoutSeconds = Annotated[float, Field(gt=0, le=300)]
MigrationLockTimeoutSeconds = Annotated[float, Field(gt=0, le=300)]


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
LogFormat = Literal["console", "json"]

BACKEND_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_ENV_FILE = BACKEND_ROOT / ".env"
DEFAULT_TEST_ENV_FILE = BACKEND_ROOT / ".env.test"


class DatabaseSettings(BaseModel):
    host: str = Field(default="localhost", min_length=1)
    port: Port = 5432
    name: str = Field(min_length=1)
    user: str = Field(min_length=1)
    password: SecretStr

    pool_size: PoolSize = 10
    max_overflow: PoolOverflow = 20

    connect_timeout_seconds: ConnectTimeoutSeconds = 5
    startup_timeout_seconds: StartupTimeoutSeconds = 10.0
    pool_timeout_seconds: PoolTimeoutSeconds = 30.0
    migration_lock_timeout_seconds: MigrationLockTimeoutSeconds = 5.0


class Settings(BaseSettings):
    environment: Literal["local", "test", "production"] = "local"
    log_level: LogLevel = "INFO"
    log_format: LogFormat = "console"

    database: DatabaseSettings

    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="INFRAMELD_",
        env_nested_delimiter="__",
        extra="forbid",
    )


def _format_validation_error(error: ValidationError) -> str:
    details = "\n".join(
        f"- {'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors()
    )
    return f"Invalid runtime configuration:\n{details}"


def _settings_env_file() -> Path | None:
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
def get_settings() -> Settings:
    """Load and cache validated application settings."""
    try:
        return Settings(_env_file=_settings_env_file())  # pyright: ignore[reportCallIssue]
    except ValidationError as error:
        raise RuntimeError(_format_validation_error(error)) from None
