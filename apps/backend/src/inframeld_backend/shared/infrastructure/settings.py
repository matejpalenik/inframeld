from functools import lru_cache
from typing import Annotated, Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Port = Annotated[int, Field(ge=1, le=65_535)]
PoolSize = Annotated[int, Field(ge=1, le=100)]
PoolOverflow = Annotated[int, Field(ge=0, le=100)]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
LogFormat = Literal["console", "json"]


class DatabaseSettings(BaseModel):
    host: str = Field(default="localhost", min_length=1)
    port: Port = 5432
    name: str = Field(min_length=1)
    user: str = Field(min_length=1)
    password: SecretStr

    pool_size: PoolSize = 10
    max_overflow: PoolOverflow = 20


class Settings(BaseSettings):
    environment: Literal["local", "test", "production"] = "local"
    log_level: LogLevel = "INFO"
    log_format: LogFormat = "console"

    database: DatabaseSettings

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="INFRAMELD_",
        env_nested_delimiter="__",
        extra="forbid",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache validated application settings."""
    return Settings()  # pyright: ignore[reportCallIssue]
