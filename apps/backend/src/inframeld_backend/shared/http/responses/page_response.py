"""Serialize an HTTP page and its optional continuation token."""

from pydantic import BaseModel, ConfigDict, Field


class PageResponse[ItemT](BaseModel):
    """Carry public items and an explicit continuation token."""

    model_config = ConfigDict(serialize_by_alias=True)

    items: list[ItemT]
    next_cursor: str | None = Field(serialization_alias="nextCursor")
