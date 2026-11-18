from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)


class RetainedHistoryCapacityError(DependencyUnavailableError):
    """Ordinary admission cannot reserve its mandatory retained history."""
