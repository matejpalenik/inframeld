from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.value_objects.oauth_consent_request_id import (
    OAuthConsentRequestId,
)
from inframeld_backend.access.application.value_objects.oauth_login_session_id import (
    OAuthLoginSessionId,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)


class HumanOAuthCredentialRevoker(Protocol):
    """Remove individual OAuth credentials selected by a trusted cleanup workflow.

    The caller must bind each target to the correct identity and installation.
    Typed IDs alone establish neither ownership nor permission to revoke it.
    Provider calls belong outside database transactions.
    """

    @abstractmethod
    async def revoke_grant(
        self, consent_request_id: OAuthConsentRequestId, *, timeout_seconds: float
    ) -> IdentityRecoveryCleanupState:
        """Invalidate access and refresh token chains from one consent request.

        Leave other consent requests and remembered logins alone. Return
        `CONFIRMED` for acknowledged cleanup, `FAILED` for explicit rejection, or
        `UNCERTAIN` when completion cannot be established. Never return `PENDING`.
        Repeating cleanup must address the same original target.

        Raises:
            ValueError: The deadline is not finite and positive.

        Cancellation propagates and does not prove that remote cleanup stopped.
        """
        ...

    @abstractmethod
    async def revoke_login(
        self, login_session_id: OAuthLoginSessionId, *, timeout_seconds: float
    ) -> IdentityRecoveryCleanupState:
        """Forget one remembered login so that it cannot skip authentication.

        Issued token grants need separate revoke_grant calls. The provider may
        send configured logout notifications. Outcome, deadline and cancellation
        rules match revoke_grant.
        """
        ...
