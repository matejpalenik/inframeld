"""Verify safe translation of request-validation failures."""

from fastapi.exceptions import RequestValidationError

from inframeld_backend.shared.http import validation
from inframeld_backend.shared.http.problems import (
    MAX_VALIDATION_ISSUES,
    MAX_VALIDATION_PATH_SEGMENTS,
    ValidationIssue,
)

SECRET = "synthetic-secret-value"


def test_unknown_validation_category_uses_safe_fallback() -> None:
    """Replace all unreviewed validation data with fixed public values."""

    error = RequestValidationError(
        [
            {
                "type": "custom_validator_failure",
                "loc": ("body", SECRET),
                "msg": SECRET,
                "input": SECRET,
                "ctx": {"reason": SECRET},
            }
        ]
    )

    issues = validation.issues_from_request_error(error)

    assert issues == (
        ValidationIssue(
            location="body", path=(), code="invalid_value", message="Use a valid value."
        ),
    )


def test_missing_known_field_uses_required_issues() -> None:
    """Translate a missing declared field into a safe required issue."""

    error = RequestValidationError(
        [
            {
                "type": "missing",
                "loc": ("body", "displayName"),
                "msg": SECRET,
                "input": {"untrusted": SECRET},
            }
        ]
    )

    issues = validation.issues_from_request_error(error)

    assert issues == (
        ValidationIssue(
            location="body",
            path=("displayName",),
            code="required",
            message="This field is required.",
        ),
    )


def test_out_of_range_query_value_uses_fixed_issue() -> None:
    """Translate a bounded-number failure without reflecting its input."""
    error = RequestValidationError(
        [
            {
                "type": "less_than_equal",
                "loc": ("query", "limit"),
                "msg": SECRET,
                "input": SECRET,
                "ctx": {"le": 100},
            }
        ]
    )

    issues = validation.issues_from_request_error(error)

    assert issues == (
        ValidationIssue(
            location="query",
            path=("limit",),
            code="out_of_range",
            message="Use a value within the permitted range.",
        ),
    )


def test_wrong_query_parameter_type_uses_invalid_type_issue() -> None:
    """Translate a type-parsing failure without reflecting its input."""
    error = RequestValidationError(
        [
            {
                "type": "int_parsing",
                "loc": ("query", "limit"),
                "msg": SECRET,
                "input": SECRET,
            }
        ]
    )

    issues = validation.issues_from_request_error(error)

    assert issues == (
        ValidationIssue(
            location="query",
            path=("limit",),
            code="invalid_type",
            message="Use a value of the expected type.",
        ),
    )


def test_invalid_json_uses_body_level_issue() -> None:
    """Translate malformed JSON without exposing parser or body details."""
    error = RequestValidationError(
        [
            {
                "type": "json_invalid",
                "loc": ("body", 13),
                "msg": SECRET,
                "input": SECRET,
                "ctx": {"error": SECRET},
            }
        ]
    )

    issues = validation.issues_from_request_error(error)

    assert issues == (
        ValidationIssue(
            location="body",
            path=(),
            code="invalid_json",
            message="Use a valid JSON request body.",
        ),
    )


def test_submitted_extra_body_key_is_not_reflected() -> None:
    """Collapse a user-controlled extra-field name to the body level."""
    error = RequestValidationError(
        [
            {
                "type": "extra_forbidden",
                "loc": ("body", SECRET),
                "msg": SECRET,
                "input": SECRET,
            }
        ]
    )

    issues = validation.issues_from_request_error(error)

    assert issues == (
        ValidationIssue(
            location="body",
            path=(),
            code="invalid_value",
            message="Use a valid value.",
        ),
    )


def test_query_list_index_is_preserved() -> None:
    """Preserve a safe index beneath a declared query parameter."""
    error = RequestValidationError(
        [
            {
                "type": "int_parsing",
                "loc": ("query", "scores", 1),
                "msg": SECRET,
                "input": SECRET,
            }
        ]
    )

    issues = validation.issues_from_request_error(error)

    assert issues == (
        ValidationIssue(
            location="query",
            path=("scores", 1),
            code="invalid_type",
            message="Use a value of the expected type.",
        ),
    )


def test_deep_query_list_path_is_bounded() -> None:
    """Truncate a deep safe-index path to the public path limit."""
    error = RequestValidationError(
        [
            {
                "type": "int_parsing",
                "loc": (
                    "query",
                    "scores",
                    *range(MAX_VALIDATION_PATH_SEGMENTS + 4),
                ),
                "msg": SECRET,
                "input": SECRET,
            }
        ]
    )

    issues = validation.issues_from_request_error(error)

    assert issues == (
        ValidationIssue(
            location="query",
            path=(
                "scores",
                *range(MAX_VALIDATION_PATH_SEGMENTS - 1),
            ),
            code="invalid_type",
            message="Use a value of the expected type.",
        ),
    )


def test_validation_issue_count_is_bounded() -> None:
    """Return at most the public maximum number of validation issues."""
    error = RequestValidationError(
        [
            {
                "type": "custom_validator_failure",
                "loc": ("body",),
                "msg": SECRET,
                "input": SECRET,
            }
            for _ in range(MAX_VALIDATION_ISSUES + 5)
        ]
    )

    issues = validation.issues_from_request_error(error)

    expected_issue = ValidationIssue(
        location="body",
        path=(),
        code="invalid_value",
        message="Use a valid value.",
    )
    assert issues == (expected_issue,) * MAX_VALIDATION_ISSUES
