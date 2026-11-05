from pydantic_settings import BaseSettings, SettingsConfigDict

from inframeld_backend.access.infrastructure.settings.recovery_notification_settings import (
    RecoveryNotificationSettings,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.types.log_format import LogFormat
from inframeld_backend.shared.infrastructure.types.log_level import LogLevel


class RecoveryApplicationSettings(BaseSettings):
    """Load only the resources needed by private native recovery delivery."""

    database: DatabaseSettings
    recovery: RecoveryNotificationSettings
    log_level: LogLevel = LogLevel.INFO
    log_format: LogFormat = LogFormat.CONSOLE

    model_config = SettingsConfigDict(
        env_prefix="INFRAMELD_",
        env_nested_delimiter="__",
        extra="ignore",
        hide_input_in_errors=True,
    )
