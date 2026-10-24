from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
)


class HumanOAuthCredentialRejectedError(AuthenticationRequiredError):
    """Reject a CLI binding that became invalid after initial authentication."""
