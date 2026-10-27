from pydantic_settings import BaseSettings, SettingsConfigDict

from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.types.logging_types import LogFormat, LogLevel


class MaintenanceApplicationSettings(BaseSettings):
    database: DatabaseSettings
    log_level: LogLevel = "INFO"
    log_format: LogFormat = "console"

    model_config = SettingsConfigDict(
        env_prefix="INFRAMELD_",
        env_nested_delimiter="__",
        extra="ignore",
        hide_input_in_errors=True,
    )
