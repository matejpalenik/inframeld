from uuid import uuid4

import pytest

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import InvalidInputError
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)


def test_metadata_original_lookup_uses_its_action_and_cannot_downgrade_grant_route() -> None:
    authority = OperationLookupAuthority(
        OperationLookupAuthorityFamily.PROJECT_ACTION_USE, ActionId("edit-project-metadata")
    )
    authority.require_supported_scope(
        project_id=ProjectId(uuid4()),
        method="PATCH",
        requested_route="/v1/projects/{project_id}/metadata",
    )
    with pytest.raises(InvalidInputError):
        authority.require_supported_scope(
            project_id=ProjectId(uuid4()),
            method="POST",
            requested_route="/v1/projects/{project_id}/grants",
        )
