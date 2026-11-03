import base64
import json
from uuid import UUID

import pytest

from inframeld_backend.access.application.queries.list_project_members_query import (
    ListProjectMembersQuery,
)
from inframeld_backend.access.application.value_objects.project_members_cursor import (
    ProjectMembersCursor,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

PARTS: list[object] = [
    1,
    "project-members",
    "principal-id-asc",
    str(UUID(int=11)),
    str(UUID(int=2)),
    str(UUID(int=3)),
    str(UUID(int=20)),
]


def _token(parts: object) -> str:
    return (
        base64.urlsafe_b64encode(json.dumps(parts, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )


@pytest.mark.parametrize("value", [0, 20])
def test_cursor_round_trip_preserves_distinct_scope_and_uuid_position(value: int) -> None:
    cursor = ProjectMembersCursor(
        InstallationId(UUID(int=11)),
        OrganizationId(UUID(int=2)),
        ProjectId(UUID(int=3)),
        PrincipalId(UUID(int=value)),
    )
    token = cursor.to_token()
    assert len(token) <= 1024 and "=" not in token
    assert ProjectMembersCursor.from_token(token) == cursor
    assert json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))) == [
        *PARTS[:-1],
        str(UUID(int=value)),
    ]


@pytest.mark.parametrize(
    "position,value",
    [
        (0, True),
        (0, 1.0),
        (0, 2),
        (1, "grant-recipients"),
        (2, "display-name-asc"),
        (3, "bad-id"),
        (4, None),
        (5, 3),
        (6, "bad-id"),
    ],
)
def test_cursor_rejects_incompatible_schema_or_position(position: int, value: object) -> None:
    parts = PARTS.copy()
    parts[position] = value
    token = _token(parts)
    with pytest.raises(ValueError) as raised:
        ProjectMembersCursor.from_token(token)
    assert token not in str(raised.value)


@pytest.mark.parametrize(
    "parts", [PARTS[:-1], [*PARTS, "unexpected"], {"after": str(UUID(int=20))}, None]
)
def test_cursor_rejects_missing_extra_or_non_list_contents(parts: object) -> None:
    with pytest.raises(ValueError):
        ProjectMembersCursor.from_token(_token(parts))


@pytest.mark.parametrize(
    "token", ["", "A", "abc=", "bad+value", "bad/value", "é", "a" * 1025, "_w", "bm90LWpzb24"]
)
def test_cursor_rejects_malformed_encoding_without_exposing_it(token: str) -> None:
    with pytest.raises(ValueError) as raised:
        ProjectMembersCursor.from_token(token)
    if token:
        assert token not in str(raised.value)


@pytest.mark.parametrize("limit", [0, -1, 101, True])
def test_application_query_rejects_invalid_limits(limit: int) -> None:
    with pytest.raises(ValueError):
        ListProjectMembersQuery(ProjectId(UUID(int=3)), limit)


@pytest.mark.parametrize("cursor", ["", "a" * 1025, "bad+value", "padded="])
def test_application_query_rejects_invalid_cursor_syntax(cursor: str) -> None:
    with pytest.raises(ValueError):
        ListProjectMembersQuery(ProjectId(UUID(int=3)), cursor=cursor)
