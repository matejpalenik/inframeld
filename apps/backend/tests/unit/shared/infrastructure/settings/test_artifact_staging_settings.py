from pathlib import Path

import pytest
from pydantic import ValidationError

from inframeld_backend.shared.infrastructure.settings.artifact_staging_settings import (
    ArtifactStagingSettings,
)


def test_relative_root_cannot_select_caller_working_directory() -> None:
    with pytest.raises(ValidationError):
        ArtifactStagingSettings(root=Path("relative"))
