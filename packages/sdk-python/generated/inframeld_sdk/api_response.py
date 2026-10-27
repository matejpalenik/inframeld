"""API response object."""

from __future__ import annotations
from typing import Optional, Generic, Mapping, TypeVar
import httpx
from pydantic import Field, StrictInt, StrictBytes, BaseModel, field_validator, field_serializer

T = TypeVar("T")

class ApiResponse(BaseModel, Generic[T]):
    """
    API response object
    """

    status_code: StrictInt = Field(description="HTTP status code")
    headers: Optional[httpx.Headers] = Field(None, description="HTTP headers")
    data: T = Field(description="Deserialized data given the data type")
    raw_data: StrictBytes = Field(description="Raw data (HTTP response body)")

    model_config = {
        "arbitrary_types_allowed": True
    }

    @field_validator("headers", mode="before")
    @classmethod
    def preserve_headers(cls, value: object) -> httpx.Headers | None:
        if value is None or isinstance(value, httpx.Headers):
            return value
        return httpx.Headers(value)

    @field_serializer("headers", when_used="json")
    def serialize_headers(self, value: httpx.Headers | None) -> list[tuple[str, str]] | None:
        return value.multi_items() if value is not None else None
