from uuid import UUID

import pytest

from inframeld_backend.access.application.queries.list_project_action_grants_query import (
    ListProjectActionGrantsQuery,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@pytest.mark.parametrize("limit", [-1, 0, 101, True, 1.5])
def test_page_limit_is_an_exact_bounded_integer(limit: int) -> None:
    with pytest.raises(ValueError):
        ListProjectActionGrantsQuery(ProjectId(UUID(int=1)), ActionId("inspect-budget"), limit)


@pytest.mark.parametrize("cursor", ["", "a" * 1025, "a=", "a/b", " "])
def test_cursor_syntax_is_bounded(cursor: str) -> None:
    with pytest.raises(ValueError):
        ListProjectActionGrantsQuery(
            ProjectId(UUID(int=1)), ActionId("inspect-budget"), cursor=cursor
        )
