from uuid import UUID

import pytest
from pydantic import ValidationError
from tests.support.mock_project_metadata import ORGANIZATION_ID, PROJECT_ID

from inframeld_backend.access.application.dtos.project_metadata_dto import ProjectMetadataDTO
from inframeld_backend.access.http.mappers.project_metadata_mapper import ProjectMetadataMapper
from inframeld_backend.access.http.requests.project_metadata_update_request import (
    ProjectMetadataUpdateRequest,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


def test_selector_only_input_omits_legacy_label_replacement() -> None:
    request = ProjectMetadataUpdateRequest(expectedMetadataRevision=0, name="support")
    command = ProjectMetadataMapper.to_command(UUID(int=3), request)
    assert command.name == ResourceName("support")
    assert command.display_name is None


@pytest.mark.parametrize(
    "extra",
    [
        {"name": None},
        {"displayName": None},
        {},
        {"displayName": " "},
        {"displayName": "a" * 129},
        {"name": "Support"},
    ],
)
def test_invalid_or_null_submitted_replacements_are_rejected(extra: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ProjectMetadataUpdateRequest.model_validate({"expectedMetadataRevision": 0, **extra})


def test_response_preserves_legacy_label_without_new_input_validation() -> None:
    label = " legacy\nlabel " + "a" * 1000
    response = ProjectMetadataMapper.metadata(
        ProjectMetadataDTO(ORGANIZATION_ID, PROJECT_ID, None, label, 0)
    )
    assert response.display_name == label
    assert response.name is None


@pytest.mark.parametrize("name", [ResourceName("research"), None])
def test_retired_name_problem_contains_only_authorized_safe_identity_guidance(
    name: ResourceName | None,
) -> None:
    from inframeld_backend.access.application.errors.retired_project_name_error import (
        RetiredProjectNameError,
    )
    from inframeld_backend.shared.http.definitions.problem_catalogue import (
        RESOURCE_NOT_FOUND_PROBLEM,
    )

    problem = ProjectMetadataMapper.retired(RetiredProjectNameError(PROJECT_ID, name))
    assert problem.status == 404 and problem.code == RESOURCE_NOT_FOUND_PROBLEM.code
    assert str(PROJECT_ID.value) in problem.detail
    assert ("research" if name is not None else "no current Name") in problem.detail
    assert len(problem.detail) <= 512
