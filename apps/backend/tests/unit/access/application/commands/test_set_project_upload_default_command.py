from typing import cast

import pytest
from tests.support.mock_project_metadata import PROJECT_ID
from tests.support.mock_project_upload_defaults import NEW

from inframeld_backend.access.application.commands.set_project_upload_default_command import (
    SetProjectUploadDefaultCommand,
)


@pytest.mark.parametrize("revision", [-1, 9007199254740992, True, 1.5, None])
def test_review_revision_must_be_an_exact_safe_nonnegative_integer(revision: object) -> None:
    with pytest.raises((ValueError, TypeError)):
        SetProjectUploadDefaultCommand(PROJECT_ID, NEW, cast(int, revision))
