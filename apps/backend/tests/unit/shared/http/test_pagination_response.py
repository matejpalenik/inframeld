"""Check the public pagination response shape."""

from inframeld_backend.shared.http.pagination import PageResponse


def test_page_with_more_items_uses_next_cursor_wire_name() -> None:
    """A client can find the token for its next request."""
    page = PageResponse[int](items=[1, 2], next_cursor="YWJj")

    assert page.model_dump(mode="json") == {
        "items": [1, 2],
        "nextCursor": "YWJj",
    }


def test_last_page_has_null_next_cursor() -> None:
    """A client can tell when it should stop requesting pages."""
    page = PageResponse[int](items=[], next_cursor=None)

    assert page.model_dump(mode="json") == {
        "items": [],
        "nextCursor": None,
    }
