import base64
import json
from uuid import UUID

import pytest

from inframeld_backend.access.application.enums.my_project_access_item_kind import (
    MyProjectAccessItemKind,
)
from inframeld_backend.access.application.value_objects.my_project_access_cursor import (
    MyProjectAccessCursor,
)
from inframeld_backend.access.application.value_objects.my_project_access_position import (
    MyProjectAccessPosition,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@pytest.mark.parametrize(
    "position",
    [
        MyProjectAccessPosition(
            MyProjectAccessItemKind.GRANT, UUID(int=5), ActionId("inspect-budget")
        ),
        MyProjectAccessPosition(MyProjectAccessItemKind.MEMBERSHIP, UUID(int=5), None),
        MyProjectAccessPosition(MyProjectAccessItemKind.MANAGEMENT, UUID(int=5), None),
    ],
)
def test_cursor_round_trip_preserves_person_scope_and_relationship_position(
    position: MyProjectAccessPosition,
) -> None:
    cursor = MyProjectAccessCursor(
        InstallationId(UUID(int=1)),
        OrganizationId(UUID(int=2)),
        ProjectId(UUID(int=3)),
        PrincipalId(UUID(int=4)),
        position,
    )
    token = cursor.to_token()
    assert MyProjectAccessCursor.from_token(token) == cursor
    assert "=" not in token and len(token) <= 1024


@pytest.mark.parametrize(
    "parts",
    [
        [],
        [True],
        [2],
        [1, "another-endpoint", "combined-v1", *([str(UUID(int=1))] * 5), "grant", "query"],
        [1, "my-project-access", "wrong-order", *([str(UUID(int=1))] * 5), "grant", "query"],
        [1, "my-project-access", "combined-v1", *([str(UUID(int=1))] * 5), "grant", None],
        [1, "my-project-access", "combined-v1", *([str(UUID(int=1))] * 5), "membership", "query"],
    ],
)
def test_incompatible_or_incoherent_cursor_cannot_resume(parts: list[object]) -> None:
    token = base64.urlsafe_b64encode(json.dumps(parts).encode()).decode().rstrip("=")
    with pytest.raises(ValueError):
        MyProjectAccessCursor.from_token(token)


@pytest.mark.parametrize("token", ["", "x" * 1025, "padded=", "not_valid", "é"])
def test_malformed_token_is_rejected(token: str) -> None:
    with pytest.raises(ValueError):
        MyProjectAccessCursor.from_token(token)


def test_combined_order_does_not_reset_the_limit_at_each_relationship_array() -> None:
    grant = MyProjectAccessPosition(
        MyProjectAccessItemKind.GRANT, UUID(int=999), ActionId("inspect-budget")
    )
    membership = MyProjectAccessPosition(MyProjectAccessItemKind.MEMBERSHIP, UUID(int=1), None)
    management = MyProjectAccessPosition(MyProjectAccessItemKind.MANAGEMENT, UUID(int=1), None)
    assert grant.sort_key < membership.sort_key < management.sort_key
