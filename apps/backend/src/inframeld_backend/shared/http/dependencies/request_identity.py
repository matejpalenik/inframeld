"""Narrow Starlette's dynamic request state at the HTTP boundary."""

from typing import cast
from uuid import uuid4

from starlette.requests import Request

from inframeld_backend.shared.application.value_objects.request_id import RequestId


def request_identity(request: Request) -> RequestId:
    """Read the server-generated request ID, creating a stable fallback if middleware was bypassed."""
    raw = cast(object, getattr(request.state, "request_id", None))
    if isinstance(raw, RequestId):
        return raw
    identity = RequestId(uuid4())
    request.state.request_id = identity
    return identity
