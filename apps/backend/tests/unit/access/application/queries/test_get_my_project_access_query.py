from typing import cast
from uuid import UUID

import pytest

from inframeld_backend.access.application.queries.get_my_project_access_query import (
    GetMyProjectAccessQuery,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId

PROJECT = ProjectId(UUID(int=3))


def test_own_read_defaults_to_a_bounded_page_without_principal_selector() -> None:
    query = GetMyProjectAccessQuery(PROJECT)
    assert (query.project_id, query.limit, query.cursor) == (PROJECT, 25, None)


@pytest.mark.parametrize("limit", [0, 101, -1, True, 1.0, "25"])
def test_invalid_combined_page_limits_are_rejected(limit: object) -> None:
    with pytest.raises(ValueError):
        GetMyProjectAccessQuery(PROJECT, cast(int, limit))


@pytest.mark.parametrize("cursor", ["", "a" * 1025, "with space", "padded=", "é"])
def test_invalid_cursor_syntax_is_rejected_before_reader_work(cursor: str) -> None:
    with pytest.raises(ValueError):
        GetMyProjectAccessQuery(PROJECT, cursor=cursor)
