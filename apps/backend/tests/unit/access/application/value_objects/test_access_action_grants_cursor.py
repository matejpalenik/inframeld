"""Retain concrete scope and action in an opaque bounded continuation position."""

import base64
import json
from uuid import UUID

import pytest

from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.value_objects.access_action_grants_cursor import (
    AccessActionGrantsCursor,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

ORG = OrganizationId(UUID(int=2))
PROJECT = ProjectId(UUID(int=3))


@pytest.mark.parametrize(
    "target,action",
    [
        (OrganizationGrantTargetDTO(organization_id=ORG), "create-projects"),
        (
            AccessGroupGrantTargetDTO(
                project_id=PROJECT, access_group_id=AccessGroupId(UUID(int=4))
            ),
            "add-documents",
        ),
        (
            ApplicationAccountGrantTargetDTO(
                project_id=PROJECT, application_principal_id=PrincipalId(UUID(int=5))
            ),
            "issue-application-keys",
        ),
    ],
)
def test_round_trip_preserves_all_concrete_scope_and_position(
    target: OrganizationGrantTargetDTO
    | AccessGroupGrantTargetDTO
    | ApplicationAccountGrantTargetDTO,
    action: str,
) -> None:
    cursor = AccessActionGrantsCursor(
        installation_id=InstallationId(UUID(int=1)),
        organization_id=ORG,
        target=target,
        action_id=ActionId(action),
        after=PrincipalId(UUID(int=6)),
    )
    assert AccessActionGrantsCursor.from_token(cursor.to_token()) == cursor
    assert "=" not in cursor.to_token()


@pytest.mark.parametrize("token", ["", "!not-base64", "x" * 1025, "e30", "W10"])
def test_malformed_or_unbounded_cursor_is_rejected(token: str) -> None:
    with pytest.raises(ValueError):
        AccessActionGrantsCursor.from_token(token)


@pytest.mark.parametrize(
    "version,kind,project",
    [
        (True, "organization", None),
        (2, "organization", None),
        (1, "pipeline", str(PROJECT.value)),
        (1, "access_group", str(PROJECT.value)),
        (1, "organization", str(PROJECT.value)),
        (1, "access-group", None),
        (1, "application-account", None),
    ],
)
def test_incompatible_family_version_or_scope_never_becomes_a_new_position(
    version: int | bool, kind: str, project: str | None
) -> None:
    parts = [
        version,
        "access-action-grants",
        "recipient-id-asc",
        str(UUID(int=1)),
        str(ORG.value),
        kind,
        project,
        str(UUID(int=4)),
        "add-documents",
        str(UUID(int=6)),
    ]
    token = base64.urlsafe_b64encode(json.dumps(parts).encode()).decode().rstrip("=")
    with pytest.raises(ValueError):
        AccessActionGrantsCursor.from_token(token)
