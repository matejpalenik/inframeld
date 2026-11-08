from typing import override

from inframeld_backend.access.application.dtos.invitation_browser_proof_dto import (
    InvitationBrowserProofDTO,
)
from inframeld_backend.access.application.protocols.invitation_session_verifier import (
    InvitationSessionVerifier,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)


class MockInvitationSessionVerifier(InvitationSessionVerifier):
    """Control provider proof and observe profile selection without provider I/O."""

    def __init__(self, proof: InvitationBrowserProofDTO | None) -> None:
        self.proof = proof
        self.error: Exception | None = None
        self.calls: list[tuple[BrowserSessionCredential, bool]] = []

    @override
    async def verify(
        self,
        credential: BrowserSessionCredential,
        *,
        observe_password_completion: bool = False,
    ) -> InvitationBrowserProofDTO | None:
        self.calls.append((credential, observe_password_completion))
        if self.error is not None:
            raise self.error
        return self.proof
