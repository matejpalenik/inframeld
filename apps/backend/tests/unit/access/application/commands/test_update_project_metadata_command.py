from uuid import uuid4

import pytest

from inframeld_backend.access.application.commands.update_project_metadata_command import (
    UpdateProjectMetadataCommand,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@pytest.mark.parametrize("revision", [-1, True, 1.0])
def test_rejects_invalid_review_revision(revision: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        UpdateProjectMetadataCommand(ProjectId(uuid4()), revision)  # type: ignore[arg-type]


def test_requires_an_explicit_replacement_field() -> None:
    with pytest.raises(ValueError):
        UpdateProjectMetadataCommand(ProjectId(uuid4()), 0)
