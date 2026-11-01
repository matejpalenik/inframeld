from uuid import uuid4

import pytest

from inframeld_backend.access.domain.entities.project_metadata import ProjectMetadata
from inframeld_backend.access.domain.errors.project_metadata_errors import (
    ProjectMetadataStaleRevisionError,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


@pytest.mark.parametrize("legacy", ["", " ", "a" * 1000, "legacy\x00\nlabel"])
def test_first_selector_allocation_keeps_unrestricted_legacy_label(legacy: str) -> None:
    project = ProjectMetadata(
        project_id=ProjectId(uuid4()),
        organization_id=OrganizationId(uuid4()),
        name=None,
        display_name=legacy,
        revision=0,
    )
    original_id = project.project_id
    assert project.change(expected_revision=0, name=ResourceName("support"), display_name=None)
    assert (project.project_id, project.name, project.display_name, project.revision) == (
        original_id,
        ResourceName("support"),
        legacy,
        1,
    )


def test_stale_combined_rename_changes_neither_field() -> None:
    project = ProjectMetadata(
        project_id=ProjectId(uuid4()),
        organization_id=OrganizationId(uuid4()),
        name=ResourceName("support"),
        display_name="Support",
        revision=3,
    )
    with pytest.raises(ProjectMetadataStaleRevisionError):
        project.change(
            expected_revision=2,
            name=ResourceName("legal"),
            display_name=SubmittedDisplayName("Legal"),
        )
    assert (project.name, project.display_name, project.revision) == (
        ResourceName("support"),
        "Support",
        3,
    )
