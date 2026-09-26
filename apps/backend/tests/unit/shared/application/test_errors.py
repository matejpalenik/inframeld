"""Check default and caller-supplied diagnostic messages for application errors."""

from collections.abc import Callable

import pytest

from inframeld_backend.shared.application.application_error import ApplicationError
from inframeld_backend.shared.application.errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)

DEFAULT_ERROR_CASES: tuple[tuple[Callable[[], ApplicationError], str], ...] = (
    (lambda: InvalidInputError(), "The supplied input is invalid for this operation."),
    (lambda: ResourceNotFoundError(), "The requested resource is not available."),
    (lambda: AccessDeniedError(), "The requested action is not permitted."),
    (lambda: ConflictError(), "The operation conflicts with the current state."),
    (
        lambda: DependencyUnavailableError(),
        "A required dependency is temporarily unavailable.",
    ),
)


@pytest.mark.parametrize(
    ("error_factory", "expected_message"),
    DEFAULT_ERROR_CASES,
    ids=("invalid-input", "not-found", "access-denied", "conflict", "dependency"),
)
def test_error_uses_its_default_message_when_none_is_supplied(
    error_factory: Callable[[], ApplicationError], expected_message: str
) -> None:
    """Use the error category's generic diagnostic when no message is provided."""
    error = error_factory()

    assert error.message == expected_message
    assert str(error) == expected_message


def test_each_error_accepts_a_specific_diagnostic_message() -> None:
    """Keep a caller's more useful internal diagnostic when one is provided."""
    message = "The operation failed in this specific context."
    errors = (
        InvalidInputError(message),
        ResourceNotFoundError(message),
        AccessDeniedError(message),
        ConflictError(message),
        DependencyUnavailableError(message),
    )

    assert all(error.message == message and str(error) == message for error in errors)
