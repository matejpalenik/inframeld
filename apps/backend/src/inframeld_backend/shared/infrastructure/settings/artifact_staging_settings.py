from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ArtifactStagingSettings(BaseSettings):
    """Select an existing private root, never an automatically replaced empty store."""

    root: Path

    model_config = SettingsConfigDict(
        env_prefix="INFRAMELD_ARTIFACT_STAGING__", extra="ignore", hide_input_in_errors=True
    )

    @field_validator("root")
    @classmethod
    def require_absolute_root(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("Private staging requires an absolute existing root.")
        return value
