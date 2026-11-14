from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ProviderCredentialSettings(BaseModel):
    """Locate a provisioned root key and its separately trusted SHA-256 identity."""

    key_file: Path | None = None
    expected_key_id: str | None = None

    model_config = ConfigDict(hide_input_in_errors=True)
