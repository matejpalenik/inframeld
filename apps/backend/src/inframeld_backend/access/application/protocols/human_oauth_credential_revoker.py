from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject


class HumanOAuthCredentialRevoker(Protocol):
    """Remove a recovering human's CLI grants and remembered OAuth logins.

    The caller must establish the subject's provider and installation binding.
    A typed subject alone establishes neither ownership nor permission to revoke.
    Provider calls belong outside database transactions.
    """

    @abstractmethod
    async def revoke_cli_grants(
        self, subject: IdentitySubject, *, timeout_seconds: float
    ) -> IdentityRecoveryCleanupState:
        """Invalidate this human's access and refresh grants for the Inframeld CLI.

        Leave other humans, other clients and remembered logins alone. Return
        `CONFIRMED` for acknowledged cleanup, `FAILED` for explicit rejection, or
        `UNCERTAIN` when completion cannot be established. Never return `PENDING`.
        A retry may also revoke credentials obtained since the previous attempt.

        Raises:
            ValueError: The deadline is not finite and positive.

        Cancellation propagates and does not prove that remote cleanup stopped.
        """
        ...

    @abstractmethod
    async def revoke_remembered_logins(
        self, subject: IdentitySubject, *, timeout_seconds: float
    ) -> IdentityRecoveryCleanupState:
        """Forget all of this human's remembered OAuth logins, across clients.

        Issued tokens need separate revoke_cli_grants calls. Kratos browser
        sessions remain separate. A retry may forget a newer remembered login.
        Outcome, deadline and cancellation rules match revoke_cli_grants.
        """
        ...
