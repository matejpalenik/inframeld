from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.invitation_browser_proof_dto import (
    InvitationBrowserProofDTO,
)
from inframeld_backend.access.application.dtos.invitation_preview_result_dto import (
    InvitationPreviewResultDTO,
)
from inframeld_backend.access.application.queries.preview_invitation_query import (
    PreviewInvitationQuery,
)


class InvitationPreviewer(Protocol):
    @abstractmethod
    async def preview(
        self, *, proof: InvitationBrowserProofDTO, query: PreviewInvitationQuery
    ) -> InvitationPreviewResultDTO:
        """Read safe valid intent for a currently admissible verified browser identity.

        The browser profile verified the cookie and CSRF before this call. No
        password observation, reservation, admission or assignment belongs here.
        Preview cannot promise that a later activation will remain valid.
        """
        ...
