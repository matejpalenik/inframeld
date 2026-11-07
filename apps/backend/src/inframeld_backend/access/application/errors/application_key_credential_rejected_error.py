from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
)


class ApplicationKeyCredentialRejectedError(AuthenticationRequiredError):
    """Reject a key that became invalid before the protected operation."""
