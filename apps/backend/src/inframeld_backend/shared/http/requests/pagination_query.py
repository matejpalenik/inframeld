"""Shared HTTP pagination parameters."""

from pydantic import BaseModel, Field


class PaginationQuery(BaseModel):
    """Parse the common pagination parameters of a list request."""

    limit: int = Field(default=25, ge=1, le=100)
    cursor: str | None = Field(
        default=None,
        min_length=1,
        max_length=1024,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
