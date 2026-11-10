import pytest
from tests.support.mock_project_metadata import ORGANIZATION_ID, PROJECT_ID
from tests.support.mock_project_upload_defaults import NEW, OLD

from inframeld_backend.access.domain.entities.project_upload_default import ProjectUploadDefault
from inframeld_backend.access.domain.errors.project_upload_default_errors import (
    ProjectUploadDefaultStaleRevisionError,
)
from inframeld_backend.shared.domain.errors.domain_errors import InvalidStateTransitionError
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


def test_replace_changes_only_future_default_and_its_revision() -> None:
    default = ProjectUploadDefault(
        organization_id=ORGANIZATION_ID, project_id=PROJECT_ID, audience=OLD, access_revision=7
    )
    assert default.replace(audience=NEW, expected_access_revision=7)
    assert default.audience == NEW
    assert default.access_revision == 8
    assert default.project_id == PROJECT_ID


def test_fresh_equal_set_still_requires_current_review() -> None:
    default = ProjectUploadDefault(
        organization_id=ORGANIZATION_ID, project_id=PROJECT_ID, audience=OLD, access_revision=7
    )
    with pytest.raises(ProjectUploadDefaultStaleRevisionError):
        default.replace(audience=OLD, expected_access_revision=6)
    assert default.audience == OLD
    assert default.access_revision == 7


def test_equal_set_does_not_advance_even_at_maximum_revision() -> None:
    default = ProjectUploadDefault(
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
        audience=OLD,
        access_revision=RevisionValidation.MAX_VALUE,
    )
    assert not default.replace(audience=OLD, expected_access_revision=RevisionValidation.MAX_VALUE)
    assert default.access_revision == RevisionValidation.MAX_VALUE


def test_changed_set_cannot_overflow() -> None:
    default = ProjectUploadDefault(
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
        audience=OLD,
        access_revision=RevisionValidation.MAX_VALUE,
    )
    with pytest.raises(InvalidStateTransitionError):
        default.replace(audience=NEW, expected_access_revision=RevisionValidation.MAX_VALUE)
    assert default.audience == OLD
