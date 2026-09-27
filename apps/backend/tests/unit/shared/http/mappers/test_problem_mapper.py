"""Verify explicit mappings from application errors to HTTP problems."""

import pytest

from inframeld_backend.shared.application.errors.application_error import (
    ApplicationError,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.http.definitions.problem_catalogue import (
    ACCESS_DENIED_PROBLEM,
    CONFLICT_PROBLEM,
    DEPENDENCY_UNAVAILABLE_PROBLEM,
    INTERNAL_ERROR_PROBLEM,
    INVALID_INPUT_PROBLEM,
    RESOURCE_NOT_FOUND_PROBLEM,
)
from inframeld_backend.shared.http.definitions.problem_definition import ProblemDefinition
from inframeld_backend.shared.http.mappers import problem_mapper


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (InvalidInputError("Diagnostic only."), INVALID_INPUT_PROBLEM),
        (ResourceNotFoundError("Diagnostic only."), RESOURCE_NOT_FOUND_PROBLEM),
        (AccessDeniedError("Diagnostic only."), ACCESS_DENIED_PROBLEM),
        (ConflictError("Diagnostic only."), CONFLICT_PROBLEM),
        (
            DependencyUnavailableError("Diagnostic only."),
            DEPENDENCY_UNAVAILABLE_PROBLEM,
        ),
    ],
)
def test_maps_supported_concrete_application_errors(
    error: ApplicationError, expected: ProblemDefinition
) -> None:
    """Map each supported concrete application error explicitly."""

    assert problem_mapper.for_application_error(error) == expected


def test_maps_unregistered_subclass_to_internal_error() -> None:
    """Do not inherit a parent exception's public HTTP mapping."""

    class UnregisteredConflictError(ConflictError):
        """Represent an unreviewed subtype that must not inherit public exposure implicitly."""

        pass

    error = UnregisteredConflictError("Diagnostic only.")

    assert problem_mapper.for_application_error(error) == INTERNAL_ERROR_PROBLEM
