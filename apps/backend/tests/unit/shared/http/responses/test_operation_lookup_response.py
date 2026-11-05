"""Keep known references distinct from unknown dispatch and protected job details."""

import pytest
from pydantic import ValidationError

from inframeld_backend.shared.http.responses.accepted_operation_lookup_response import (
    AcceptedOperationLookupResponse,
)
from inframeld_backend.shared.http.responses.completed_operation_lookup_response import (
    CompletedOperationLookupResponse,
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


def test_accepted_lookup_serializes_known_product_job_reference() -> None:
    known = ACCEPTED | {"jobReference": {"jobId": "00000000-0000-4000-8000-000000000008"}}
    result = AcceptedOperationLookupResponse.model_validate(known)
    assert result.model_dump(by_alias=True, mode="json") == known


@pytest.mark.parametrize(
    "reference",
    [
        None,
        "known",
        {},
        {"jobId": None},
        {"jobId": "not-a-uuid"},
        {"jobId": "00000000-0000-4000-8000-000000000008", "state": "running"},
    ],
)
def test_accepted_lookup_rejects_malformed_or_overbroad_job_reference(reference: object) -> None:
    with pytest.raises(ValidationError):
        AcceptedOperationLookupResponse.model_validate(ACCEPTED | {"jobReference": reference})


@pytest.mark.parametrize("value", [None, "guessed-job"])
def test_accepted_lookup_forbids_an_extra_job_identifier(value: str | None) -> None:
    with pytest.raises(ValidationError):
        AcceptedOperationLookupResponse.model_validate(ACCEPTED | {"jobId": value})


@pytest.mark.parametrize("classification", ["safe_result", "issued_secret", "answer_receipt"])
def test_completed_lookup_keeps_each_supported_classification_on_the_wire(
    classification: str,
) -> None:
    body = {
        "outcome": "completed_synchronous",
        "operationId": "original-operation",
        "classification": classification,
        "idempotencyExpiresAt": "2030-01-01T00:00:00Z",
    }
    result = CompletedOperationLookupResponse.model_validate(body)
    assert result.model_dump(by_alias=True, mode="json") == body


@pytest.mark.parametrize("classification", ["async_job", "unknown", None])
def test_completed_lookup_rejects_classifications_outside_its_exact_subset(
    classification: str | None,
) -> None:
    with pytest.raises(ValidationError):
        CompletedOperationLookupResponse.model_validate(
            {
                "outcome": "completed_synchronous",
                "operationId": "original-operation",
                "classification": classification,
                "idempotencyExpiresAt": "2030-01-01T00:00:00Z",
            }
        )
