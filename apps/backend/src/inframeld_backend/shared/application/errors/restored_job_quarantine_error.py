from inframeld_backend.shared.application.errors.application_errors import ConflictError


class RestoredJobQuarantineError(ConflictError):
    """Refuse unconfirmed scope, changed work or an unavailable original receipt."""
