"""Verify the public problem representation and its output bounds."""

import pytest
from pydantic import ValidationError

from inframeld_backend.shared.http.problems import ProblemDetails

REQUEST_ID = "c66a2044-4e4f-4c07-983e-a3c221c7b1ad"
TYPE_PREFIX = (
    "https://github.com/matejpalenik/inframeld/blob/main/docs/development/error-handling.md"
)


def _payload() -> dict[str, object]:
    """Return synthetic server-owned data for the initial validation problem."""
    return {
        "type": f"{TYPE_PREFIX}#validation-error",
        "title": "Request validation failed",
        "status": 422,
        "detail": "One or more request fields are invalid.",
        "code": "validation_error",
        "request_id": REQUEST_ID,
        "errors": [
            {
                "location": "query",
                "path": ["limit"],
                "code": "out_of_range",
                "message": "Use a value within the permitted range.",
            }
        ],
    }


def test_serializes_public_request_id_and_issue_path() -> None:
    """Emit camel-case wire names, a UUID string, and JSON array paths."""
    problem = ProblemDetails.model_validate(_payload())

    result = problem.model_dump(mode="json", by_alias=True, exclude_none=True)

    assert result == {
        "type": f"{TYPE_PREFIX}#validation-error",
        "title": "Request validation failed",
        "status": 422,
        "detail": "One or more request fields are invalid.",
        "code": "validation_error",
        "requestId": REQUEST_ID,
        "errors": [
            {
                "location": "query",
                "path": ["limit"],
                "code": "out_of_range",
                "message": "Use a value within the permitted range.",
            }
        ],
    }


def test_rejects_undeclared_response_fields() -> None:
    """Reject accidental metadata that has no reviewed public contract."""
    payload = _payload()
    payload["providerKey"] = "synthetic-test-only"

    with pytest.raises(ValidationError):
        ProblemDetails.model_validate(payload)


def test_rejects_more_than_twenty_validation_issues() -> None:
    """Enforce the model's bound; the translator will truncate before this."""
    payload = _payload()
    payload["errors"] = [
        {
            "location": "body",
            "path": [],
            "code": "invalid_value",
            "message": "A supplied value is invalid.",
        }
        for _ in range(21)
    ]

    with pytest.raises(ValidationError):
        ProblemDetails.model_validate(payload)


def test_accepts_about_blank_problem_type() -> None:
    """Accepts RFC 9457's generic problem-type identifier"""
    payload = _payload()
    payload["type"] = "about:blank"

    problem = ProblemDetails.model_validate(payload)

    result = problem.model_dump(mode="json", by_alias=True, exclude_none=True)

    assert result["type"] == "about:blank"


def test_rejects_relative_problem_type() -> None:
    """Require problem types other than about:blank to be absolute URIs."""
    payload = _payload()
    payload["type"] = "relative-problem"

    with pytest.raises(ValidationError):
        ProblemDetails.model_validate(payload)


@pytest.mark.parametrize("status", [400, 599])
def test_accepts_http_error_status_boundaries(status: int) -> None:
    """Accept the inclusive HTTP error-status boundaries."""
    payload = _payload()
    payload["status"] = status

    problem = ProblemDetails.model_validate(payload)

    assert problem.status == status


@pytest.mark.parametrize("status", [399, 600, True])
def test_rejects_invalid_http_error_status(status: object) -> None:
    """Reject statuses outside the error range and non-strict integers."""
    payload = _payload()
    payload["status"] = status

    with pytest.raises(ValidationError):
        ProblemDetails.model_validate(payload)


@pytest.mark.parametrize(
    "path",
    [[0], ["field"] * 8],
)
def test_accepts_validation_issue_path_boundaries(path: list[str | int]) -> None:
    """Accept non-negative indices and paths up to eight segments."""
    payload = _payload()
    payload["errors"] = [
        {
            "location": "body",
            "path": path,
            "code": "invalid_value",
            "message": "A supplied value is invalid",
        }
    ]

    problem = ProblemDetails.model_validate(payload)

    assert problem.errors is not None
    assert list(problem.errors[0].path) == path


@pytest.mark.parametrize(
    "path",
    [[-1], ["field"] * 9],
)
def test_rejects_invalid_validation_issue_paths(path: list[str | int]) -> None:
    """Reject negative indices and paths longer than eight segments"""
    payload = _payload()
    payload["errors"] = [
        {
            "location": "body",
            "path": path,
            "code": "invalid_value",
            "message": "A supplied value is invalid",
        }
    ]

    with pytest.raises(ValidationError):
        ProblemDetails.model_validate(payload)


def test_rejects_undeclared_validation_issue_fields() -> None:
    """Reject unreviewed metadata inside individual validation issues."""
    payload = _payload()
    payload["errors"] = [
        {
            "location": "body",
            "path": ["field"],
            "code": "invalid_value",
            "message": "A supplied value is invalid.",
            "providerKey": "synthetic-test-only",
        }
    ]

    with pytest.raises(ValidationError):
        ProblemDetails.model_validate(payload)


def test_rejects_validation_path_field_names_longer_than_sixty_four_characters() -> None:
    """Bound public field names included in validation paths."""
    payload = _payload()
    payload["errors"] = [
        {
            "location": "body",
            "path": ["x" * 65],
            "code": "invalid_value",
            "message": "A supplied value is invalid.",
        }
    ]

    with pytest.raises(ValidationError):
        ProblemDetails.model_validate(payload)


@pytest.mark.parametrize(
    "code",
    [
        "INVALID_VALUE",
        "1invalid_value",
        "invalid-value",
        "x" * 65,
    ],
)
def test_rejects_invalid_error_codes(code: str) -> None:
    """Require bounded lower-snake-case validation codes."""
    payload = _payload()
    payload["errors"] = [
        {
            "location": "body",
            "path": [],
            "code": code,
            "message": "A supplied value is invalid.",
        }
    ]

    with pytest.raises(ValidationError):
        ProblemDetails.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", ""),
        ("title", "x" * 129),
        ("detail", ""),
        ("detail", "x" * 513),
    ],
)
def test_rejects_invalid_public_text_lengths(field: str, value: str) -> None:
    """Enforce the public title and detail bounds."""
    payload = _payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        ProblemDetails.model_validate(payload)


@pytest.mark.parametrize("message", ["", "x" * 257])
def test_rejects_invalid_validation_issue_message_lengths(message: str) -> None:
    """Enforce the validation-issue message bounds."""
    payload = _payload()
    payload["errors"] = [
        {
            "location": "body",
            "path": [],
            "code": "invalid_value",
            "message": message,
        }
    ]

    with pytest.raises(ValidationError):
        ProblemDetails.model_validate(payload)


def test_rejects_problem_type_longer_than_2048_characters() -> None:
    """Bound the public problem-type URI."""
    payload = _payload()
    payload["type"] = f"https://example.com/{'x' * 2050}"

    with pytest.raises(ValidationError):
        ProblemDetails.model_validate(payload)


def test_omits_absent_validation_issues_from_public_output() -> None:
    """Omit the optional errors member from non-validation problems."""
    payload = _payload()
    payload.pop("errors")

    problem = ProblemDetails.model_validate(payload)

    result = problem.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert "errors" not in result
