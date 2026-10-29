"""Keep unknown job references explicit without a redundant job identifier field."""

import pytest
from pydantic import ValidationError

from inframeld_backend.shared.http.responses.accepted_operation_lookup_response import (
    AcceptedOperationLookupResponse,
)

ACCEPTED = {
    "outcome": "accepted_asynchronous",
    "operationId": "original-operation",
    "admission": "confirmed",
    "jobReference": "unknown",
    "dispatch": "not_established",
    "idempotencyExpiresAt": None,
}


def test_accepted_lookup_serializes_explicit_uncertainty_without_a_job_id() -> None:
    result = AcceptedOperationLookupResponse.model_validate(ACCEPTED)
    assert result.model_dump(by_alias=True, mode="json") == ACCEPTED


@pytest.mark.parametrize("value", [None, "guessed-job"])
def test_accepted_lookup_forbids_an_extra_job_identifier(value: str | None) -> None:
    with pytest.raises(ValidationError):
        AcceptedOperationLookupResponse.model_validate(ACCEPTED | {"jobId": value})
