"""Bound the reviewed values allowed in public problem responses."""

from typing import Annotated

from pydantic import AnyUrl, Field, UrlConstraints

from inframeld_backend.shared.http.enums.validation_issue_location import ValidationIssueLocation

MAX_VALIDATION_ISSUES = 20
MAX_VALIDATION_PATH_SEGMENTS = 8

ProblemType = Annotated[AnyUrl, UrlConstraints(max_length=2048)]
FieldName = Annotated[str, Field(min_length=1, max_length=64)]
ArrayIndex = Annotated[int, Field(ge=0, strict=True)]
IssueLocation = ValidationIssueLocation
ErrorCode = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")]
