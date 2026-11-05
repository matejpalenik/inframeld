from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from inframeld_backend.shared.infrastructure.settings.artifact_staging_settings import (
    ArtifactStagingSettings,
)
from inframeld_backend.shared.infrastructure.settings.artifact_storage_settings import (
    ArtifactStorageSettings,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.settings.job_settings import JobSettings
from inframeld_backend.shared.infrastructure.types.logging_types import LogFormat, LogLevel


class ApplicationWorkerApplicationSettings(BaseSettings):
    database: DatabaseSettings
    artifact_storage: ArtifactStorageSettings
    artifact_staging: ArtifactStagingSettings
    jobs: JobSettings = Field(default_factory=JobSettings)
    log_level: LogLevel = "INFO"
    log_format: LogFormat = "console"

    model_config = SettingsConfigDict(
        env_prefix="INFRAMELD_",
        env_nested_delimiter="__",
        extra="ignore",
        hide_input_in_errors=True,
    )
