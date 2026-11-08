from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.invitation_browser_proof_dto import (
    InvitationBrowserProofDTO,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)


class InvitationSessionVerifier(Protocol):
    """Verify recipient identity before local admission without retaining the session secret."""

    @abstractmethod
    async def verify(
        self,
        credential: BrowserSessionCredential,
        *,
        observe_password_completion: bool = False,
    ) -> InvitationBrowserProofDTO | None:
        """Verify the cookie and optionally observe current stored password-verifier presence.

        Preview performs no password observation. Completed current-recipient replay
        ignores an absent or unavailable fact. Only fresh activation requires true,
        independent of the login method. All calls share the original provider budget.
        The private SDK call, parsing and boolean reduction stay in one confidential
        boundary. No configuration, hash or payload-bearing exception may escape.
        Refuse unsafe wire debugging, preserve safe known failures and unexpected
        failure/cancellation semantics, and do not promise memory zeroization.
        Return None for rejected sessions or a positively deleted/inactive identity.
        Malformed or contradictory identity evidence raises DependencyUnavailableError.
        This check grants no local admission.
        """
        ...
