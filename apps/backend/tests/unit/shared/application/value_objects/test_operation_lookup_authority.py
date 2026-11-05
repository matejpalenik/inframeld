from uuid import UUID, uuid4

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


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize("action", ["inspect-budget", "edit-project-metadata"])
def test_full_project_grant_lookup_keeps_exact_delegation_authority(
    method: str, action: str
) -> None:
    project = ProjectId(UUID(int=3))
    route = f"/v1/projects/{project.value}/grants/{UUID(int=4)}/{action}"
    OperationLookupAuthority(
        OperationLookupAuthorityFamily.PROJECT_GRANT_READ, ActionId(action)
    ).require_supported_scope(project_id=project, method=method, requested_route=route)


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_full_grant_route_cannot_be_downgraded_to_ordinary_use(method: str) -> None:
    project = ProjectId(UUID(int=3))
    authority = OperationLookupAuthority(
        OperationLookupAuthorityFamily.PROJECT_ACTION_USE, ActionId("inspect-budget")
    )
    with pytest.raises(InvalidInputError):
        authority.require_supported_scope(
            project_id=project,
            method=method,
            requested_route=f"/v1/projects/{project.value}/grants/{UUID(int=4)}/inspect-budget",
        )


@pytest.mark.parametrize(
    "route",
    [
        f"/v1/projects/{UUID(int=9)}/grants/{UUID(int=4)}/inspect-budget",
        f"/v1/projects/{UUID(int=3)}/grants/{UUID(int=4)}/manage-budget",
        f"/v1/projects/{UUID(int=3)}/grants/not-a-principal/inspect-budget",
        f"/v1/projects/{UUID(int=3)}/grants/{UUID(int=4)}/inspect-budget/extra",
        f"/v1/projects/{UUID(int=3)}/grants/{UUID(int=4)}/inspect-budget?other=1",
    ],
)
def test_full_grant_lookup_rejects_changed_scope_action_or_route(route: str) -> None:
    with pytest.raises(InvalidInputError):
        OperationLookupAuthority(
            OperationLookupAuthorityFamily.PROJECT_GRANT_READ, ActionId("inspect-budget")
        ).require_supported_scope(
            project_id=ProjectId(UUID(int=3)), method="PUT", requested_route=route
        )


def test_legacy_post_still_accepts_only_its_published_action_and_method() -> None:
    project = ProjectId(UUID(int=3))
    OperationLookupAuthority(
        OperationLookupAuthorityFamily.PROJECT_GRANT_READ, ActionId("create-access-groups")
    ).require_supported_scope(
        project_id=project, method="POST", requested_route="/v1/projects/{project_id}/grants"
    )
    for method, action in (("PUT", "create-access-groups"), ("POST", "inspect-budget")):
        with pytest.raises(InvalidInputError):
            OperationLookupAuthority(
                OperationLookupAuthorityFamily.PROJECT_GRANT_READ, ActionId(action)
            ).require_supported_scope(
                project_id=project,
                method=method,
                requested_route="/v1/projects/{project_id}/grants",
            )
