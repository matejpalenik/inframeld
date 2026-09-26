"""Verify runtime validation of request and operation correlation values."""

from typing import cast
from uuid import UUID

import pytest

from inframeld_backend.shared.application.correlation.operation_id import OperationId
from inframeld_backend.shared.application.correlation.request_id import RequestId


def test_request_id_requires_uuid() -> None:
    """Reject unparsed request IDs even when a caller bypasses static checking."""
    with pytest.raises(TypeError, match="UUID"):
        RequestId(cast(UUID, "unparsed"))


def test_operation_id_rejects_blank_text() -> None:
    """Preserve opaque identifiers while rejecting a missing operation identity."""
    assert OperationId("synthetic-operation-id").value == "synthetic-operation-id"
    with pytest.raises(ValueError):
        OperationId(" ")
