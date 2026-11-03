from inframeld_backend.shared.application.errors.application_errors import ConflictError


class SpendingLimitExceededError(ConflictError):
    pass


class IncompleteSpendingFactsError(ConflictError):
    pass
