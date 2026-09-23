"""Shared HTTP pagination parameters."""

from pydantic import BaseModel, ConfigDict, Field


class PaginationQuery(BaseModel):
    """Parse the common pagination parameters of a list request."""

    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = Field(
        default=None,
        min_length=1,
        max_length=1024,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


class PageResponse[ItemT](BaseModel):
    """Carry public items and an explicit continuation token."""

    model_config = ConfigDict(serialize_by_alias=True)

    items: list[ItemT]
    next_cursor: str | None = Field(serialization_alias="nextCursor")
