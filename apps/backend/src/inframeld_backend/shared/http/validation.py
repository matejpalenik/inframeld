"""Translate FastAPI request-validation failures into safe public issues.

The translator reads each framework error once, retains only the error type and
location needed for classification, and builds a new bounded ValidationIssue.
Raw messages, submitted values, and validator context are never exposed.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self, cast

from fastapi.exceptions import RequestValidationError

from inframeld_backend.shared.http.problems import (
    MAX_VALIDATION_ISSUES,
    MAX_VALIDATION_PATH_SEGMENTS,
    IssueLocation,
    ValidationIssue,
)

# Mirrors the FieldName constraint in problems.py.
_MAX_PUBLIC_FIELD_NAME_LENGTH = 64

_ISSUE_LOCATION_BY_RAW_VALUE: dict[str, IssueLocation] = {
    "body": "body",
    "path": "path",
    "query": "query",
    "header": "header",
    "cookie": "cookie",
    "request": "request",
}


def issues_from_request_error(
    error: RequestValidationError,
) -> tuple[ValidationIssue, ...]:
    """Translate a FastAPI validation failure into bounded public issues.

    The function processes at most ``MAX_VALIDATION_ISSUES`` entries. Each raw
    framework error is normalized before translation so that unsafe fields such
    as ``msg``, ``input``, and ``ctx`` cannot flow into the public response.

    Args:
        error: FastAPI request-validation failure containing untrusted details.

    Returns:
        Fresh validation issues containing only approved locations, bounded
        paths, stable product codes, and fixed public messages.
    """
    parsed_failures = (
        _ValidationFailure.from_raw(raw_error)
        for raw_error in error.errors()[:MAX_VALIDATION_ISSUES]
    )

    return tuple(failure.to_public_issue() for failure in parsed_failures)


@dataclass(frozen=True, slots=True)
class _ValidationFailure:
    """Hold the minimal data needed to translate one validation error.

    This private value separates parsing of FastAPI/Pydantic data from creation
    of the public error contract. It deliberately does not retain raw messages,
    submitted input, validator context, or documentation URLs.

    Attributes:
        pydantic_type: Pydantic's machine-readable category, or ``None`` when
            the raw value is missing or malformed.
        location: Approved request component, falling back to ``request`` when
            the raw location is missing or unsupported.
        candidate_path: Bounded but still untrusted path components after the
            request location. These values must never be logged or emitted
            without applying one of the path-sanitization policies below.
    """

    pydantic_type: str | None
    location: IssueLocation
    candidate_path: tuple[object, ...]

    @classmethod
    def from_raw(cls, raw_error: object) -> Self:
        """Normalize one loosely typed FastAPI/Pydantic error dictionary.

        Only ``type`` and ``loc`` are retained. An unsupported location
        collapses to the request level so that unknown path components cannot
        reach a public response.

        Args:
            raw_error: One untrusted entry returned by
                ``RequestValidationError.errors()``.

        Returns:
            A bounded internal representation suitable for safe translation.
        """
        if not isinstance(raw_error, Mapping):
            return cls(
                pydantic_type=None,
                location="request",
                candidate_path=(),
            )

        error_mapping = cast(Mapping[object, object], raw_error)

        raw_type = error_mapping.get("type")
        pydantic_type = raw_type if isinstance(raw_type, str) else None

        raw_location = error_mapping.get("loc")

        if not isinstance(raw_location, (list, tuple)) or not raw_location:
            return cls(
                pydantic_type=pydantic_type,
                location="request",
                candidate_path=(),
            )

        location_parts = cast(
            list[object] | tuple[object, ...],
            raw_location,
        )
        raw_location_name = location_parts[0]

        location = (
            _ISSUE_LOCATION_BY_RAW_VALUE.get(raw_location_name)
            if isinstance(raw_location_name, str)
            else None
        )

        if location is None:
            return cls(
                pydantic_type=pydantic_type,
                location="request",
                candidate_path=(),
            )

        return cls(
            pydantic_type=pydantic_type,
            location=location,
            candidate_path=tuple(location_parts[1 : MAX_VALIDATION_PATH_SEGMENTS + 1]),
        )

    def to_public_issue(self) -> ValidationIssue:
        """Translate this normalized failure into one safe public issue.

        Every supported Pydantic category is explicitly mapped to an
        Inframeld-owned code and fixed message. Unrecognized categories use the
        conservative generic fallback.

        Returns:
            A newly constructed issue containing no submitted values or raw
            framework messages.
        """
        match self.pydantic_type:
            case "missing":
                return ValidationIssue(
                    location=self.location,
                    path=self._missing_field_path(),
                    code="required",
                    message="This field is required.",
                )

            case "less_than_equal":
                return ValidationIssue(
                    location=self.location,
                    path=self._parameter_path(),
                    code="out_of_range",
                    message="Use a value within the permitted range.",
                )

            case "int_parsing":
                return ValidationIssue(
                    location=self.location,
                    path=self._parameter_path(),
                    code="invalid_type",
                    message="Use a value of the expected type.",
                )

            case "json_invalid":
                return ValidationIssue(
                    location="body",
                    path=(),
                    code="invalid_json",
                    message="Use a valid JSON request body.",
                )

            case _:
                return ValidationIssue(
                    location=self.location,
                    path=(),
                    code="invalid_value",
                    message="Use a valid value.",
                )

    def _missing_field_path(self) -> tuple[str, ...]:
        """Return one bounded field name for a top-level missing-field error.

        A deeper path is discarded because nested body locations may contain
        submitted dictionary keys that are unsafe to reflect.

        Returns:
            A one-segment field path when it is safe, otherwise an empty path.
        """
        if len(self.candidate_path) != 1:
            return ()

        field_name = self._first_bounded_field_name()

        return (field_name,) if field_name is not None else ()

    def _parameter_path(self) -> tuple[str | int, ...]:
        """Return a declared non-body parameter plus safe list indices.

        The declared parameter name is preserved only for path, query, header,
        and cookie inputs. Following non-negative integers are safe list
        positions. Processing stops before any string or unsupported value that
        could represent a submitted dictionary key.

        Returns:
            A bounded public parameter path, or an empty path when unsafe.
        """
        if self.location not in ("path", "query", "header", "cookie"):
            return ()

        field_name = self._first_bounded_field_name()

        if field_name is None:
            return ()

        safe_path: list[str | int] = [field_name]

        for part in self.candidate_path[1:]:
            if isinstance(part, bool) or not isinstance(part, int) or part < 0:
                break

            safe_path.append(part)

        return tuple(safe_path)

    def _first_bounded_field_name(self) -> str | None:
        """Return the first candidate when it is a valid public field name.

        Returns:
            The bounded field name, or ``None`` when the candidate is missing,
            has the wrong type, or exceeds the public length limit.
        """
        if not self.candidate_path:
            return None

        field_name = self.candidate_path[0]

        if (
            not isinstance(field_name, str)
            or not 1 <= len(field_name) <= _MAX_PUBLIC_FIELD_NAME_LENGTH
        ):
            return None

        return field_name
